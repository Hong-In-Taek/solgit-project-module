# solgit-project-module

GitLab 및 Jenkins 관련 서비스를 제공하는 Python 모듈입니다. RabbitMQ를 통해 메시지를 구독하고, 메시지 타입에 따라 GitLab API 또는 Jenkins API를 호출합니다.

## 기능

- RabbitMQ에서 메시지 구독
- 메시지 타입별 GitLab API 호출
  - `GL_PROJECT_FORK`: 프로젝트 fork하여 새 프로젝트 생성
  - `GL_PROJECT_ADD_MEMBER`: 프로젝트에 사용자 추가
- 메시지 타입별 Jenkins API 호출
  - `JENKINS_PROJECT_COPY`: 다른 폴더의 프로젝트를 복사하여 새 프로젝트 생성

## 구조

```
solgit-project-module/
├── api/
│   ├── gitlab_client.py      # GitLab API 클라이언트
│   └── jenkins_client.py      # Jenkins API 클라이언트
├── mq/
│   └── subscriber.py          # RabbitMQ Subscriber
├── service/
│   └── message_service.py     # 메시지 처리 서비스
├── config.py                  # 설정 관리
├── model.py                   # 메시지 모델
├── main.py                    # 메인 애플리케이션
├── requirements.txt           # Python 의존성
├── Dockerfile                 # Docker 이미지 빌드
└── .env.example               # 환경 변수 예시
```

## 설치 및 실행

### 로컬 환경

1. 의존성 설치:
```bash
pip install -r requirements.txt
```

2. 환경 변수 설정:
```bash
cp .env.example .env
# .env 파일을 편집하여 필요한 값 설정
```

3. 애플리케이션 실행:
```bash
python main.py
```

### Docker

1. Docker 이미지 빌드:
```bash
docker build -t solgit-project-module .
```

2. Docker 컨테이너 실행 (환경 변수 파일 사용):
```bash
docker run -d \
  --name solgit-project-module \
  --env-file .env \
  --restart unless-stopped \
  solgit-project-module
```

3. Docker 컨테이너 실행 (환경 변수 직접 지정 - 방법 1: GITLAB_INSTANCES 사용):
```bash
docker run -d \
  --name solgit-project-module \
  -e RABBITMQ_URL=amqp://admin:password@host.docker.internal:5672/ \
  -e CONSUME_EXCHANGE_NAME=solgit.main.exchange \
  -e CONSUME_EXCHANGE_TYPE=topic \
  -e CONSUME_QUEUE_NAME=solgit.project.q  \
  -e CONSUME_BINDING_KEY=project.create \
  -e PREFETCH_COUNT=20 \
  -e SERVICE_NAME=solgit-project-module \
  -e GITLAB_INSTANCES=GitlabAi,GitlabOnprem,Gitlab,GitlabTest \
  -e GITLAB_GITLABAI_URL=https://gitlab-ai.example.com \
  -e GITLAB_GITLABAI_TOKEN=your_gitlab_ai_token \
  -e GITLAB_GITLABONPREM_URL=https://gitlab-onprem.example.com \
  -e GITLAB_GITLABONPREM_TOKEN=your_gitlab_onprem_token \
  -e GITLAB_GITLAB_URL=https://gitlab.com \
  -e GITLAB_GITLAB_TOKEN=your_gitlab_token \
  -e GITLAB_GITLABTEST_URL=https://gitlab-test.example.com \
  -e GITLAB_GITLABTEST_TOKEN=your_gitlab_test_token \
  -e GITLAB_TIMEOUT=30 \
  -e JENKINS_URL=http://jenkins.example.com:8080 \
  -e JENKINS_USERNAME=admin \
  -e JENKINS_PASSWORD=your_jenkins_api_token \
  -e JENKINS_TIMEOUT=30 \
  --restart unless-stopped \
  solgit-project-module
```

4. Docker 컨테이너 실행 (환경 변수 직접 지정 - 방법 2: 기존 방식):
```bash
docker run -d \
  --name solgit-project-module \
  -e RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/ \
  -e CONSUME_EXCHANGE_NAME=app.events \
  -e CONSUME_EXCHANGE_TYPE=topic \
  -e CONSUME_QUEUE_NAME=app.worker.q \
  -e CONSUME_BINDING_KEY= \
  -e CONSUMER_WORKERS=4 \
  -e PREFETCH_COUNT=20 \
  -e SERVICE_NAME=solgit-project-module \
  -e GITLAB_AI_URL=https://gitlab-ai.example.com \
  -e GITLAB_AI_TOKEN=your_gitlab_ai_token \
  -e GITLAB_ONPREM_URL=https://gitlab-onprem.example.com \
  -e GITLAB_ONPREM_TOKEN=your_gitlab_onprem_token \
  -e GITLAB_URL=https://gitlab.com \
  -e GITLAB_TOKEN=your_gitlab_token \
  -e GITLAB_TEST_URL=https://gitlab-test.example.com \
  -e GITLAB_TEST_TOKEN=your_gitlab_test_token \
  -e GITLAB_TIMEOUT=30 \
  -e JENKINS_URL=http://jenkins.example.com:8080 \
  -e JENKINS_USERNAME=admin \
  -e JENKINS_PASSWORD=your_jenkins_api_token \
  -e JENKINS_TIMEOUT=30 \
  --restart unless-stopped \
  solgit-project-module
```

5. 컨테이너 로그 확인:
```bash
docker logs -f solgit-project-module
```

6. 컨테이너 중지 및 제거:
```bash
docker stop solgit-project-module
docker rm solgit-project-module
```

## 환경 변수

### RabbitMQ 설정
- `RABBITMQ_URL`: RabbitMQ 연결 URL (기본값: `amqp://guest:guest@localhost:5672/`)

### Subscriber 설정
- `CONSUME_EXCHANGE_NAME`: 구독할 Exchange 이름 (기본값: `app.events`)
- `CONSUME_EXCHANGE_TYPE`: Exchange 타입 (기본값: `topic`)
- `CONSUME_QUEUE_NAME`: 구독할 Queue 이름 (기본값: `app.worker.q`)
- `CONSUME_BINDING_KEY`: Binding Key (기본값: 빈 값, 모든 메시지 수신)

### Consumer 설정
- `CONSUMER_WORKERS`: Worker 스레드 수 (기본값: `4`)
- `PREFETCH_COUNT`: Prefetch 개수 (기본값: `20`)
- `SERVICE_NAME`: 서비스 이름 (기본값: `solgit-project-module`)

### GitLab API 설정
여러 GitLab 인스턴스를 지원합니다. `gitType`에 따라 사용할 GitLab을 선택합니다.

#### 방법 1: 환경변수로 인스턴스 목록 지정 (권장)
- `GITLAB_INSTANCES`: GitLab 인스턴스 목록 (쉼표로 구분, 예: `GitlabAi,GitlabOnprem,Gitlab,GitlabTest`)
- 각 인스턴스마다 다음 환경변수 설정:
  - `GITLAB_{INSTANCE}_URL`: GitLab 서버 URL
  - `GITLAB_{INSTANCE}_TOKEN`: GitLab Personal Access Token

**예시:**
```bash
GITLAB_INSTANCES=GitlabAi,GitlabOnprem,Gitlab,GitlabTest
GITLAB_GITLABAI_URL=https://gitlab-ai.example.com
GITLAB_GITLABAI_TOKEN=your_token_here
GITLAB_GITLABONPREM_URL=https://gitlab-onprem.example.com
GITLAB_GITLABONPREM_TOKEN=your_token_here
GITLAB_GITLAB_URL=https://gitlab.com
GITLAB_GITLAB_TOKEN=your_token_here
GITLAB_GITLABTEST_URL=https://gitlab-test.example.com
GITLAB_GITLABTEST_TOKEN=your_token_here
```

#### 방법 2: 기존 방식 (하위 호환성)
- `GITLAB_AI_URL`: GitlabAi 서버 URL
- `GITLAB_AI_TOKEN`: GitlabAi Personal Access Token
- `GITLAB_ONPREM_URL`: GitlabOnprem 서버 URL
- `GITLAB_ONPREM_TOKEN`: GitlabOnprem Personal Access Token
- `GITLAB_URL`: Gitlab 서버 URL (기본값: `https://gitlab.com`)
- `GITLAB_TOKEN`: Gitlab Personal Access Token
- `GITLAB_TEST_URL`: GitlabTest 서버 URL
- `GITLAB_TEST_TOKEN`: GitlabTest Personal Access Token

#### 공통 설정
- `GITLAB_TIMEOUT`: API 요청 타임아웃 (초, 기본값: `30`)

**참고**: 
- 각 GitLab 인스턴스는 URL과 TOKEN이 모두 설정되어야 사용 가능합니다.
- `GITLAB_INSTANCES`를 설정하면 해당 방식이 우선 적용되며, 기존 방식은 하위 호환성을 위해 유지됩니다.

### Jenkins API 설정
Jenkins는 단일 인스턴스만 지원합니다.

- `JENKINS_URL`: Jenkins 서버 URL (예: `http://jenkins.example.com:8080`)
- `JENKINS_USERNAME`: Jenkins 사용자명
- `JENKINS_PASSWORD`: Jenkins API Token 또는 비밀번호
- `JENKINS_TIMEOUT`: API 요청 타임아웃 (초, 기본값: `30`)

**예시:**
```bash
JENKINS_URL=http://jenkins.example.com:8080
JENKINS_USERNAME=admin
JENKINS_PASSWORD=your_api_token_here
JENKINS_TIMEOUT=30
```

## 메시지 포맷

메시지는 solgit-mattermost-module과 동일한 포맷을 사용합니다:

```json
{
  "header": {
    "messageId": "uuid",
    "messageType": "GL_PROJECT_FORK",
    "version": "v1",
    "timestamp": "2024-01-01T00:00:00Z",
    "correlationId": "optional-correlation-id",
    "source": "source-service"
  },
  "body": {
    "payload": {
      // 메시지 타입별 payload
    }
  }
}
```

## 지원하는 메시지 타입

### GL_PROJECT_FORK

프로젝트를 fork하여 새 프로젝트를 생성합니다.

**Payload:**
```json
{
  "gitType": "GitlabAi",
  "project_id": 123,
  "name": "new-project-name",
  "namespace": "optional-namespace",
  "path": "optional-path"
}
```

**필수 필드:**
- `gitType`: 사용할 GitLab 타입 (GitlabAi, GitlabOnprem, Gitlab, GitlabTest 등)
- `project_id`: Fork할 원본 프로젝트 ID
- `name`: 새로 생성될 프로젝트의 이름

**선택 필드:**
- `namespace`: Fork된 프로젝트가 생성될 namespace
- `path`: Fork된 프로젝트의 path

### GL_PROJECT_ADD_MEMBER

프로젝트에 사용자를 추가합니다.

**Payload:**
```json
{
  "gitType": "GitlabOnprem",
  "project_id": 123,
  "user_id": 456,
  "access_level": 30
}
```

**필수 필드:**
- `gitType`: 사용할 GitLab 타입 (GitlabAi, GitlabOnprem, Gitlab, GitlabTest 등)
- `project_id`: 프로젝트 ID
- `user_id`: 추가할 사용자 ID

**선택 필드:**
- `access_level`: 접근 레벨 (기본값: `30`)
  - `10`: Guest
  - `20`: Reporter
  - `30`: Developer
  - `40`: Maintainer
  - `50`: Owner

**참고:**
- `user_id`는 단일 값 또는 리스트 형태로 전달 가능합니다.
- 리스트인 경우 각 사용자에 대해 멤버 추가를 수행합니다.

**예시 (리스트):**
```json
{
  "gitType": "GitlabOnprem",
  "project_id": 123,
  "user_id": [456, 789, 101],
  "access_level": 30
}
```

### JENKINS_PROJECT_COPY

다른 폴더의 Jenkins 프로젝트를 복사하여 새 프로젝트를 생성합니다.

**Payload:**
```json
{
  "source_job_name": "/a/b/template",
  "target_folder_path": "/new/era/",
  "new_job_name": "new-era-project"
}
```

**필수 필드:**
- `source_job_name`: 복사할 원본 프로젝트 경로 (예: `/a/b/template` 또는 `a/b/template`)
- `target_folder_path`: 생성할 폴더 경로 (예: `/new/era/` 또는 `new/era/`)
- `new_job_name`: 생성할 새 프로젝트 이름 (예: `new-era-project`)

**동작 방식:**
- 원본 프로젝트: `/a/b/template`
- 대상 폴더: `/new/era/`
- 새 Job 이름: `new-era-project`
- 최종 경로: `/new/era/new-era-project`
- API 호출: `POST /job/new/job/era/createItem?name=new-era-project&mode=copy&from=a/b/template`

**예시:**
```json
{
  "header": {
    "messageId": "uuid",
    "messageType": "JENKINS_PROJECT_COPY",
    "version": "v1",
    "timestamp": "2024-01-01T00:00:00Z",
    "correlationId": "optional-correlation-id",
    "source": "source-service"
  },
  "body": {
    "payload": {
      "source_job_name": "/a/b/template",
      "target_folder_path": "/new/era/",
      "new_job_name": "new-era-project"
    }
  }
}
```

## 개발

### 새로운 메시지 타입 추가

1. `service/message_service.py`의 `handle_message` 메서드에 새로운 메시지 타입 추가:
```python
handler_map = {
    "GL_PROJECT_FORK": self._handle_project_fork,
    "GL_PROJECT_ADD_MEMBER": self._handle_project_add_member,
    "JENKINS_PROJECT_COPY": self._handle_jenkins_project_copy,
    "NEW_MESSAGE_TYPE": self._handle_new_message_type,  # 추가
}
```

2. 새로운 핸들러 메서드 구현:
```python
def _handle_new_message_type(self, context: Dict[str, Any], message: Message):
    # 핸들러 로직 구현
    pass
```

3. 필요시 `api/gitlab_client.py` 또는 `api/jenkins_client.py`에 새로운 API 메서드 추가

## 라이선스

이 프로젝트는 solgit 프로젝트의 일부입니다.
