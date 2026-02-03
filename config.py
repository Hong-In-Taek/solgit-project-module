import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    def __init__(self):
        # RabbitMQ 설정
        self.rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        
        # Subscriber 설정
        self.consume_exchange_name = os.getenv("CONSUME_EXCHANGE_NAME", os.getenv("EXCHANGE_NAME", "app.events"))
        self.consume_exchange_type = os.getenv("CONSUME_EXCHANGE_TYPE", os.getenv("EXCHANGE_TYPE", "topic"))
        self.consume_queue_name = os.getenv("CONSUME_QUEUE_NAME", os.getenv("QUEUE_NAME", "app.worker.q"))
        self.consume_binding_key = os.getenv("CONSUME_BINDING_KEY", os.getenv("BINDING_KEY", ""))
        
        # Consumer 설정
        self.prefetch_count = int(os.getenv("PREFETCH_COUNT", "20"))
        self.service_name = os.getenv("SERVICE_NAME", "solgit-project-module")
        
        # GitLab API 설정 (기본)
        self.gitlab_timeout = int(os.getenv("GITLAB_TIMEOUT", "30"))
        
        # 여러 GitLab 인스턴스 설정
        # gitType에 따라 사용할 GitLab 설정을 관리
        self.gitlab_configs = {}
        
        # 환경변수로 GitLab 인스턴스 목록 설정
        # 예: GITLAB_INSTANCES=GitlabAi,GitlabOnprem,Gitlab,GitlabTest
        gitlab_instances = os.getenv("GITLAB_INSTANCES", "")
        
        if gitlab_instances:
            # 쉼표로 구분된 인스턴스 목록 파싱
            instance_list = [inst.strip() for inst in gitlab_instances.split(",") if inst.strip()]
            
            for instance_name in instance_list:
                # 각 인스턴스마다 GITLAB_{INSTANCE}_URL, GITLAB_{INSTANCE}_TOKEN 환경변수 확인
                url_key = f"GITLAB_{instance_name.upper()}_URL"
                token_key = f"GITLAB_{instance_name.upper()}_TOKEN"
                
                url = os.getenv(url_key)
                token = os.getenv(token_key)
                
                if url and token:
                    self.gitlab_configs[instance_name] = {
                        "url": url,
                        "token": token,
                        "timeout": self.gitlab_timeout
                    }
                else:
                    # 환경변수가 없으면 경고 (하지만 계속 진행)
                    logger.warning(
                        f"GitLab instance '{instance_name}' configured in GITLAB_INSTANCES "
                        f"but missing {url_key} or {token_key}"
                    )
        
        # 하위 호환성: 기존 방식도 지원 (GITLAB_INSTANCES가 없을 때)
        # GitlabAi 설정 (하위 호환성)
        gitlab_ai_url = os.getenv("GITLAB_AI_URL")
        gitlab_ai_token = os.getenv("GITLAB_AI_TOKEN")
        if gitlab_ai_url and gitlab_ai_token and "GitlabAi" not in self.gitlab_configs:
            self.gitlab_configs["GitlabAi"] = {
                "url": gitlab_ai_url,
                "token": gitlab_ai_token,
                "timeout": self.gitlab_timeout
            }
        
        # GitlabOnprem 설정 (하위 호환성)
        gitlab_onprem_url = os.getenv("GITLAB_ONPREM_URL")
        gitlab_onprem_token = os.getenv("GITLAB_ONPREM_TOKEN")
        if gitlab_onprem_url and gitlab_onprem_token and "GitlabOnprem" not in self.gitlab_configs:
            self.gitlab_configs["GitlabOnprem"] = {
                "url": gitlab_onprem_url,
                "token": gitlab_onprem_token,
                "timeout": self.gitlab_timeout
            }
        
        # Gitlab 설정 (기본, 하위 호환성)
        gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")
        gitlab_token = os.getenv("GITLAB_TOKEN")
        if gitlab_token and "Gitlab" not in self.gitlab_configs:
            self.gitlab_configs["Gitlab"] = {
                "url": gitlab_url,
                "token": gitlab_token,
                "timeout": self.gitlab_timeout
            }
        
        # GitlabTest 설정 (하위 호환성)
        gitlab_test_url = os.getenv("GITLAB_TEST_URL")
        gitlab_test_token = os.getenv("GITLAB_TEST_TOKEN")
        if gitlab_test_url and gitlab_test_token and "GitlabTest" not in self.gitlab_configs:
            self.gitlab_configs["GitlabTest"] = {
                "url": gitlab_test_url,
                "token": gitlab_test_token,
                "timeout": self.gitlab_timeout
            }
    
    def get_gitlab_config(self, git_type: str) -> dict:
        """
        gitType에 해당하는 GitLab 설정 반환
        
        Args:
            git_type: GitLab 타입 (GitlabAi, GitlabOnprem, Gitlab, GitlabTest 등)
        
        Returns:
            GitLab 설정 딕셔너리 (url, token, timeout) 또는 None
        """
        return self.gitlab_configs.get(git_type)


def get_config() -> Config:
    return Config()
