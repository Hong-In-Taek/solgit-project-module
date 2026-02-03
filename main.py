import logging
import signal
import sys
from typing import Optional

import sys
import os

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config
from mq.subscriber import Subscriber
from service.message_service import MessageService

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Application:
    def __init__(self):
        self.config = get_config()
        self.subscriber: Optional[Subscriber] = None
        self.running = False
        
        # GitLab 설정 로드 확인
        if self.config.gitlab_configs:
            logger.info(
                f"GitLab configurations loaded: {list(self.config.gitlab_configs.keys())}"
            )
        else:
            logger.warning(
                "No GitLab configurations found. Please set environment variables."
            )
        
        # Message Service 초기화 (config 전달)
        self.message_service = MessageService(
            config=self.config,
            service_name=self.config.service_name
        )
        
        # Subscriber 초기화
        self.subscriber = Subscriber(
            rabbitmq_url=self.config.rabbitmq_url,
            exchange_name=self.config.consume_exchange_name,
            exchange_type=self.config.consume_exchange_type,
            queue_name=self.config.consume_queue_name,
            binding_key=self.config.consume_binding_key,
            prefetch_count=self.config.prefetch_count,
            message_handler=self.message_service.handle_message
        )
        
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """시그널 핸들러"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)
    
    def start(self):
        """애플리케이션 시작"""
        logger.info(
            f"Starting service - {self.config.service_name}, "
            f"queue={self.config.consume_queue_name}, "
            f"exchange={self.config.consume_exchange_name}"
        )
        
        try:
            self.running = True
            self.subscriber.start()
            
            # 메인 스레드에서 대기
            logger.info("Service started, waiting for messages...")
            while self.running:
                import time
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            self.stop()
    
    def stop(self):
        """애플리케이션 중지"""
        if not self.running:
            return
        
        logger.info("Stopping service...")
        self.running = False
        
        if self.subscriber:
            self.subscriber.stop()
        
        logger.info("Service stopped")


def main():
    app = Application()
    app.start()


if __name__ == "__main__":
    main()
