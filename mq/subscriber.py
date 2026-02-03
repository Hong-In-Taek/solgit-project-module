import json
import logging
import threading
import time
from contextlib import contextmanager
from typing import Callable, Optional

import pika
from pika.exceptions import AMQPConnectionError, AMQPChannelError

import sys
import os

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from model import Message


logger = logging.getLogger(__name__)


class Subscriber:
    def __init__(
        self,
        rabbitmq_url: str,
        exchange_name: str,
        exchange_type: str,
        queue_name: str,
        binding_key: str,
        prefetch_count: int,
        message_handler: Callable[[dict, Message], None]
    ):
        self.rabbitmq_url = rabbitmq_url
        self.exchange_name = exchange_name
        self.exchange_type = exchange_type
        self.queue_name = queue_name
        self.binding_key = binding_key or "#"  # 빈 값이면 모든 메시지 수신
        self.prefetch_count = prefetch_count
        self.message_handler = message_handler
        
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None
        self.workers: list[threading.Thread] = []
        self.running = False
        self._lock = threading.Lock()
    
    def connect(self):
        """RabbitMQ 연결 및 Exchange, Queue 설정"""
        try:
            self.connection = pika.BlockingConnection(
                pika.URLParameters(self.rabbitmq_url)
            )
            self.channel = self.connection.channel()
            
            # Exchange 선언
            self.channel.exchange_declare(
                exchange=self.exchange_name,
                exchange_type=self.exchange_type,
                durable=True
            )
            logger.info(
                f"Exchange declared: {self.exchange_name} (type: {self.exchange_type})"
            )
            
            # Queue 선언
            self.channel.queue_declare(
                queue=self.queue_name,
                durable=True
            )
            logger.info(f"Queue declared: {self.queue_name}")
            
            # Queue를 Exchange에 바인딩
            self.channel.queue_bind(
                exchange=self.exchange_name,
                queue=self.queue_name,
                routing_key=self.binding_key
            )
            logger.info(
                f"Queue bound to exchange: {self.queue_name} -> {self.exchange_name} "
                f"(binding_key: {self.binding_key})"
            )
            
            # QoS 설정
            self.channel.basic_qos(prefetch_count=self.prefetch_count)
            
        except (AMQPConnectionError, AMQPChannelError) as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    def start(self, num_workers: int = 1):
        """Subscriber 시작"""
        if self.running:
            logger.warning("Subscriber is already running")
            return
        
        if not self.connection or self.connection.is_closed:
            self.connect()
        
        self.running = True
        
        # 단일 Worker 스레드만 사용 (병렬 처리 방지)
        worker = threading.Thread(
            target=self._worker,
            args=(0,),
            daemon=True
        )
        worker.start()
        self.workers.append(worker)
        logger.info("Worker 0 started (single worker mode)")
        
        logger.info(
            f"Subscriber started: queue={self.queue_name}, "
            f"exchange={self.exchange_name}, workers=1"
        )
    
    def _worker(self, worker_id: int):
        """Worker 스레드 메인 루프"""
        while self.running:
            try:
                if not self.connection or self.connection.is_closed:
                    logger.warning(f"Worker {worker_id}: Connection closed, reconnecting...")
                    self.connect()
                
                # 메시지 소비
                method_frame, header_frame, body = self.channel.basic_get(
                    queue=self.queue_name,
                    auto_ack=False
                )
                
                if method_frame:
                    self._process_message(worker_id, method_frame, header_frame, body)
                else:
                    # 메시지가 없으면 잠시 대기
                    time.sleep(0.1)
                    
            except (AMQPConnectionError, AMQPChannelError) as e:
                logger.error(f"Worker {worker_id}: Connection error: {e}")
                time.sleep(5)  # 재연결 전 대기
                try:
                    self.connect()
                except Exception as reconnect_error:
                    logger.error(f"Worker {worker_id}: Reconnection failed: {reconnect_error}")
            except Exception as e:
                logger.error(f"Worker {worker_id}: Unexpected error: {e}", exc_info=True)
                time.sleep(1)
    
    def _process_message(self, worker_id: int, method_frame, header_frame, body: bytes):
        """메시지 처리"""
        try:
            # JSON 파싱
            message_dict = json.loads(body.decode('utf-8'))
            message = Message.from_dict(message_dict)
            
            logger.info(
                f"Worker {worker_id}: Message received - "
                f"messageId={message.header.message_id}, "
                f"messageType={message.header.message_type}, "
                f"correlationId={message.header.correlation_id}"
            )
            
            # 메시지 핸들러 호출
            try:
                self.message_handler(
                    {
                        "message_id": message.header.message_id,
                        "correlation_id": message.header.correlation_id,
                        "worker_id": worker_id
                    },
                    message
                )
                # 성공 시 ACK
                self.channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                logger.info(
                    f"Worker {worker_id}: Message processed successfully - "
                    f"messageId={message.header.message_id}"
                )
            except Exception as handler_error:
                logger.error(
                    f"Worker {worker_id}: Message handler failed - "
                    f"messageId={message.header.message_id}, error={handler_error}",
                    exc_info=True
                )
                # 실패 시 NACK (requeue=False)
                self.channel.basic_nack(
                    delivery_tag=method_frame.delivery_tag,
                    requeue=False
                )
                
        except json.JSONDecodeError as e:
            logger.error(f"Worker {worker_id}: Failed to parse message: {e}")
            self.channel.basic_nack(
                delivery_tag=method_frame.delivery_tag,
                requeue=False
            )
        except Exception as e:
            logger.error(
                f"Worker {worker_id}: Unexpected error processing message: {e}",
                exc_info=True
            )
            self.channel.basic_nack(
                delivery_tag=method_frame.delivery_tag,
                requeue=False
            )
    
    def stop(self):
        """Subscriber 중지"""
        logger.info("Stopping subscriber...")
        self.running = False
        
        # Worker 스레드 종료 대기
        for worker in self.workers:
            worker.join(timeout=5)
        
        # 연결 종료
        if self.channel and not self.channel.is_closed:
            self.channel.close()
        if self.connection and not self.connection.is_closed:
            self.connection.close()
        
        logger.info("Subscriber stopped")
    
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return (
            self.connection is not None
            and not self.connection.is_closed
            and self.channel is not None
            and not self.channel.is_closed
        )
