import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

import sys
import os
import requests

# 프로젝트 루트를 Python path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from api.gitlab_client import GitLabClient
from api.jenkins_client import JenkinsClient
from model import Message

logger = logging.getLogger(__name__)


class MessageService:
    def __init__(
        self,
        config,
        service_name: str
    ):
        self.config = config
        self.service_name = service_name
        # GitLab 클라이언트 캐시 (gitType별로 캐싱)
        self._gitlab_clients: dict[str, GitLabClient] = {}
        # Jenkins 클라이언트 캐시 (단일 인스턴스)
        self._jenkins_client: Optional[JenkinsClient] = None
    
    def handle_message(self, context: Dict[str, Any], message: Message):
        """
        메시지 처리 메인 핸들러
        
        Args:
            context: 메시지 컨텍스트 (message_id, correlation_id, worker_id 등)
            message: 처리할 메시지
        """
        message_type = message.header.message_type
        message_id = message.header.message_id
        
        logger.info(
            f"Handling message - messageId={message_id}, "
            f"messageType={message_type}, "
            f"correlationId={message.header.correlation_id}"
        )
        
        # messageType에 따라 분기 처리
        handler_map = {
            "GL_PROJECT_FORK": self._handle_project_fork,
            "GL_PROJECT_ADD_MEMBER": self._handle_project_add_member,
            "JENKINS_PROJECT_COPY": self._handle_jenkins_project_copy,
        }
        
        handler = handler_map.get(message_type)
        if handler:
            try:
                handler(context, message)
            except Exception as e:
                logger.error(
                    f"Error handling message {message_type} - "
                    f"messageId={message_id}, error={e}",
                    exc_info=True
                )
                raise
        else:
            logger.warning(
                f"Unknown message type: {message_type} - messageId={message_id}"
            )
            # 알 수 없는 메시지 타입은 성공으로 처리 (에러 발생 안 함)
    
    def _get_gitlab_client(self, git_type: str) -> Optional[GitLabClient]:
        """
        gitType에 해당하는 GitLab 클라이언트 반환 (캐싱)
        
        Args:
            git_type: GitLab 타입 (GitlabAi, GitlabOnprem, Gitlab, GitlabTest 등)
        
        Returns:
            GitLabClient 인스턴스 또는 None
        """
        # 캐시에 있으면 반환
        if git_type in self._gitlab_clients:
            return self._gitlab_clients[git_type]
        
        # 설정에서 GitLab 정보 가져오기
        gitlab_config = self.config.get_gitlab_config(git_type)
        if not gitlab_config:
            logger.warning(
                f"GitLab config not found for gitType: {git_type}"
            )
            return None
        
        # GitLab 클라이언트 생성 및 캐싱
        client = GitLabClient(
            base_url=gitlab_config["url"],
            token=gitlab_config["token"],
            timeout=gitlab_config["timeout"]
        )
        self._gitlab_clients[git_type] = client
        
        logger.info(
            f"GitLab client created for gitType: {git_type}, "
            f"url={gitlab_config['url']}"
        )
        
        return client
    
    def _handle_project_fork(self, context: Dict[str, Any], message: Message):
        """프로젝트 fork 처리"""
        logger.info(
            f"Processing GL_PROJECT_FORK - messageId={message.header.message_id}"
        )
        
        payload = message.body.payload
        if not isinstance(payload, dict):
            logger.warning(
                f"Invalid payload format for GL_PROJECT_FORK - "
                f"messageId={message.header.message_id}"
            )
            return
        
        # gitType 확인
        git_type = payload.get("gitType")
        if not git_type:
            logger.warning(
                f"Missing gitType in payload - "
                f"messageId={message.header.message_id}"
            )
            return
        
        # GitLab 클라이언트 가져오기
        gitlab_client = self._get_gitlab_client(git_type)
        if not gitlab_client:
            logger.error(
                f"GitLab client not available for gitType: {git_type} - "
                f"messageId={message.header.message_id}"
            )
            return
        
        # 필수 필드 확인
        project_id = payload.get("projectId")
        if not project_id:
            logger.warning(
                f"Missing project_id in payload - "
                f"messageId={message.header.message_id}"
            )
            return
        
        name = payload.get("name")
        if not name:
            logger.warning(
                f"Missing name in payload - "
                f"messageId={message.header.message_id}"
            )
            return
        
        # 선택적 필드
        namespace_id = payload.get("namespaceId")
        path = payload.get("path")
        
        # GitLab API 호출
        result = gitlab_client.fork_project(
            project_id=int(project_id),
            namespace_id=namespace_id,
            name=name,
            path=path
        )
        
        logger.info(
            f"Successfully processed GL_PROJECT_FORK - "
            f"messageId={message.header.message_id}, "
            f"gitType={git_type}, "
            f"forkedProjectId={result.get('id')}"
        )
        
        # Backend API 호출하여 PROJECT_UPDATE 메시지 발행
        try:
            self._publish_project_update(result, payload)
        except Exception as e:
            logger.error(
                f"Failed to publish PROJECT_UPDATE message - "
                f"messageId={message.header.message_id}, "
                f"error={e}",
                exc_info=True
            )
            # Backend API 호출 실패는 경고로만 처리 (fork는 성공했으므로)
    
    def _handle_project_add_member(self, context: Dict[str, Any], message: Message):
        """프로젝트에 사용자 추가 처리"""
        logger.info(
            f"Processing GL_PROJECT_ADD_MEMBER - "
            f"messageId={message.header.message_id}"
        )
        
        payload = message.body.payload
        if not isinstance(payload, dict):
            logger.warning(
                f"Invalid payload format for GL_PROJECT_ADD_MEMBER - "
                f"messageId={message.header.message_id}"
            )
            return
        
        # gitType 확인
        git_type = payload.get("gitType")
        if not git_type:
            logger.warning(
                f"Missing gitType in payload - "
                f"messageId={message.header.message_id}"
            )
            return
        
        # GitLab 클라이언트 가져오기
        gitlab_client = self._get_gitlab_client(git_type)
        if not gitlab_client:
            logger.error(
                f"GitLab client not available for gitType: {git_type} - "
                f"messageId={message.header.message_id}"
            )
            return
        
        # 필수 필드 확인
        project_id = payload.get("projectId")
        user_id = payload.get("userIds")
        
        if not project_id or not user_id:
            logger.warning(
                f"Missing required fields in payload - "
                f"messageId={message.header.message_id}, "
                f"project_id={project_id}, user_id={user_id}"
            )
            return
        
        # 선택적 필드 (기본값: Developer = 30)
        access_level = payload.get("access_level", 30)
        
        # user_id가 리스트인지 확인
        if isinstance(user_id, list):
            # 리스트인 경우 각 user_id에 대해 처리
            results = []
            success_user_ids = []
            for uid in user_id:
                try:
                    result = gitlab_client.add_project_member(
                        project_id=int(project_id),
                        user_id=int(uid),
                        access_level=int(access_level)
                    )
                    results.append(result)
                    success_user_ids.append(str(uid))
                    logger.info(
                        f"Successfully added member - "
                        f"messageId={message.header.message_id}, "
                        f"gitType={git_type}, "
                        f"projectId={project_id}, userId={uid}, "
                        f"memberId={result.get('id')}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to add member - "
                        f"messageId={message.header.message_id}, "
                        f"gitType={git_type}, "
                        f"projectId={project_id}, userId={uid}, "
                        f"error={e}",
                        exc_info=True
                    )
            
            logger.info(
                f"Successfully processed GL_PROJECT_ADD_MEMBER (list) - "
                f"messageId={message.header.message_id}, "
                f"gitType={git_type}, "
                f"projectId={project_id}, "
                f"totalUsers={len(user_id)}, "
                f"successCount={len(results)}"
            )
            
            # Backend API 호출하여 PROJECT_USER_UPDATE 메시지 발행
            if success_user_ids:
                try:
                    self._publish_project_user_update(
                        project_id=str(project_id),
                        git_type=git_type,
                        user_ids=success_user_ids
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to publish PROJECT_USER_UPDATE message - "
                        f"messageId={message.header.message_id}, "
                        f"error={e}",
                        exc_info=True
                    )
                    # Backend API 호출 실패는 경고로만 처리 (멤버 추가는 성공했으므로)
        else:
            # 단일 값인 경우 기존 로직
            result = gitlab_client.add_project_member(
                project_id=int(project_id),
                user_id=int(user_id),
                access_level=int(access_level)
            )
            
            logger.info(
                f"Successfully processed GL_PROJECT_ADD_MEMBER - "
                f"messageId={message.header.message_id}, "
                f"gitType={git_type}, "
                f"projectId={project_id}, userId={user_id}, "
                f"memberId={result.get('id')}"
            )
            
            # Backend API 호출하여 PROJECT_USER_UPDATE 메시지 발행
            try:
                self._publish_project_user_update(
                    project_id=str(project_id),
                    git_type=git_type,
                    user_ids=[str(user_id)]
                )
            except Exception as e:
                logger.error(
                    f"Failed to publish PROJECT_USER_UPDATE message - "
                    f"messageId={message.header.message_id}, "
                    f"error={e}",
                    exc_info=True
                )
                # Backend API 호출 실패는 경고로만 처리 (멤버 추가는 성공했으므로)
    
    def _get_jenkins_client(self) -> Optional[JenkinsClient]:
        """
        Jenkins 클라이언트 반환 (캐싱)
        
        Returns:
            JenkinsClient 인스턴스 또는 None
        """
        # 캐시에 있으면 반환
        if self._jenkins_client:
            return self._jenkins_client
        
        # 설정에서 Jenkins 정보 가져오기
        jenkins_config = self.config.get_jenkins_config()
        if not jenkins_config:
            logger.warning("Jenkins config not found")
            return None
        
        # Jenkins 클라이언트 생성 및 캐싱
        client = JenkinsClient(
            base_url=jenkins_config["url"],
            username=jenkins_config["username"],
            password=jenkins_config["password"],
            timeout=jenkins_config["timeout"]
        )
        self._jenkins_client = client
        
        logger.info(
            f"Jenkins client created - url={jenkins_config['url']}"
        )
        
        return client
    
    def _handle_jenkins_project_copy(self, context: Dict[str, Any], message: Message):
        """Jenkins 프로젝트 복사 처리"""
        logger.info(
            f"Processing JENKINS_PROJECT_COPY - "
            f"messageId={message.header.message_id}"
        )
        
        payload = message.body.payload
        if not isinstance(payload, dict):
            logger.warning(
                f"Invalid payload format for JENKINS_PROJECT_COPY - "
                f"messageId={message.header.message_id}"
            )
            return
        
        # Jenkins 클라이언트 가져오기
        jenkins_client = self._get_jenkins_client()
        if not jenkins_client:
            logger.error(
                f"Jenkins client not available - "
                f"messageId={message.header.message_id}"
            )
            return
        
        # 필수 필드 확인
        source_job_name = payload.get("sourceJobName")
        target_folder_path = payload.get("targetFolderPath")
        new_job_name = payload.get("newJobName")
        
        if not source_job_name or not target_folder_path or not new_job_name:
            logger.warning(
                f"Missing required fields in payload - "
                f"messageId={message.header.message_id}, "
                f"source_job_name={source_job_name}, "
                f"target_folder_path={target_folder_path}, "
                f"new_job_name={new_job_name}"
            )
            return
        
        # Jenkins API 호출
        result = jenkins_client.copy_project(
            source_job_name=source_job_name,
            target_folder_path=target_folder_path,
            new_job_name=new_job_name
        )
        
        final_path = f"{target_folder_path.rstrip('/')}/{new_job_name}".lstrip('/')
        logger.info(
            f"Successfully processed JENKINS_PROJECT_COPY - "
            f"messageId={message.header.message_id}, "
            f"sourceJobName={source_job_name}, "
            f"targetFolder={target_folder_path}, "
            f"newJobName={new_job_name}, "
            f"finalPath={final_path}, "
            f"jobUrl={result.get('url', 'N/A')}"
        )
    
    def _publish_project_update(self, gitlab_result: Dict[str, Any], original_payload: Dict[str, Any]):
        """
        Backend API를 호출하여 PROJECT_UPDATE 메시지 발행
        
        Args:
            gitlab_result: GitLab API의 fork_project 결과
            original_payload: 원본 메시지의 payload
        """
        backend_url = self.config.backend_api_base_url
        api_url = f"{backend_url}/api/messages/publish"
        
        # GitLab result를 ProjectUpdatePayload 형식으로 변환
        payload = self._convert_gitlab_result_to_payload(gitlab_result, original_payload)
        
        # 요청 본문 구성
        request_body = {
            "routingKey": "support.update",
            "messageType": "PROJECT_UPDATE",
            "payload": payload
        }
        
        # HTTP 헤더 설정
        headers = {
            "Content-Type": "application/json"
        }
        
        logger.info(f"Publishing PROJECT_UPDATE message to backend API - url: {api_url}")
        
        # API 호출
        response = requests.post(
            api_url,
            json=request_body,
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status()
        
        response_data = response.json()
        if response_data.get("success"):
            logger.info(
                f"PROJECT_UPDATE message published successfully - "
                f"messageId: {response_data.get('messageId')}"
            )
        else:
            error_msg = response_data.get("error", "Unknown error")
            logger.error(f"Failed to publish PROJECT_UPDATE message - error: {error_msg}")
            raise Exception(f"Failed to publish PROJECT_UPDATE: {error_msg}")
    
    def _publish_project_user_update(
        self,
        project_id: str,
        git_type: str,
        user_ids: List[str]
    ):
        """
        Backend API를 호출하여 PROJECT_USER_UPDATE 메시지 발행
        
        Args:
            project_id: 프로젝트 ID
            git_type: GitLab 타입
            user_ids: 사용자 ID 리스트
        """
        backend_url = self.config.backend_api_base_url
        api_url = f"{backend_url}/api/messages/publish"
        
        # ProjectUserUpdatePayload 형식으로 변환
        payload = {
            "projectId": project_id,
            "gitType": git_type,
            "userIds": user_ids
        }
        
        # 요청 본문 구성
        request_body = {
            "routingKey": "support.update",
            "messageType": "PROJECT_USER_UPDATE",
            "payload": payload
        }
        
        # HTTP 헤더 설정
        headers = {
            "Content-Type": "application/json"
        }
        
        logger.info(
            f"Publishing PROJECT_USER_UPDATE message to backend API - "
            f"url: {api_url}, projectId: {project_id}, userIds: {user_ids}"
        )
        
        # API 호출
        response = requests.post(
            api_url,
            json=request_body,
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status()
        
        response_data = response.json()
        if response_data.get("success"):
            logger.info(
                f"PROJECT_USER_UPDATE message published successfully - "
                f"messageId: {response_data.get('messageId')}"
            )
        else:
            error_msg = response_data.get("error", "Unknown error")
            logger.error(f"Failed to publish PROJECT_USER_UPDATE message - error: {error_msg}")
            raise Exception(f"Failed to publish PROJECT_USER_UPDATE: {error_msg}")
    
    def _convert_gitlab_result_to_payload(
        self,
        gitlab_result: Dict[str, Any],
        original_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        GitLab API result를 ProjectUpdatePayload 형식으로 변환
        
        Args:
            gitlab_result: GitLab API의 fork_project 결과
            original_payload: 원본 메시지의 payload
        
        Returns:
            ProjectUpdatePayload 형식의 딕셔너리
        """
        # GitLab result에서 필요한 정보 추출
        project_id = str(gitlab_result.get("id", ""))
        project_nm = gitlab_result.get("name", "")
        
        # namespace 정보 추출
        namespace = gitlab_result.get("namespace", {})
        # group_id = str(namespace.get("id", "")) if namespace else ""
        # group_nm = namespace.get("name", "") if namespace else ""
        
        # # parent namespace 정보 추출 (있는 경우)
        parent_namespace = namespace.get("parent", {}) if namespace else {}
        parent_group_id = str(parent_namespace.get("id", "")) if parent_namespace else None
        # parent_group_nm = parent_namespace.get("name", "") if parent_namespace else None
        
        # created_at을 LocalDateTime 형식으로 변환
        # created_at = gitlab_result.get("created_at")
        # create_dttm = None
        # if created_at:
        #     try:
        #         # ISO 8601 형식의 문자열을 파싱
        #         create_dttm = datetime.fromisoformat(created_at.replace("Z", "+00:00")).isoformat()
        #     except Exception as e:
        #         logger.warning(f"Failed to parse created_at: {created_at}, error: {e}")
        
        # # updated_at을 LocalDateTime 형식으로 변환
        # updated_at = gitlab_result.get("last_activity_at") or gitlab_result.get("updated_at")
        # update_dttm = None
        # if updated_at:
        #     try:
        #         update_dttm = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).isoformat()
        #     except Exception as e:
        #         logger.warning(f"Failed to parse updated_at: {updated_at}, error: {e}")
        
        # 원본 payload에서 추가 정보 가져오기 (있는 경우)
        create_user_id = original_payload.get("createUserId")
        update_user_id = original_payload.get("updateUserId")
        env_grp_nm = original_payload.get("gitType")
             # payload 구성
        payload = {
            "project_id": project_id,
            "project_nm": project_nm,
            "env_grp_nm": env_grp_nm
        }
        if "groupId" in original_payload:
            payload["group_id"] = original_payload.get("groupId")
        if "groupNm" in original_payload:
            payload["group_nm"] = original_payload.get("groupNm")

   
        if "parentGroupId" in original_payload:
            payload["parent_group_id"] = original_payload.get("parentGroupId")
        else:
            payload["parent_group_id"] = parent_group_id
        if "parentGroupNm" in original_payload:
            payload["parent_group_nm"] = original_payload.get("parentGroupNm")
        if "createUserId" in original_payload:
            payload["create_user_id"] = original_payload.get("createUserId")
        if "createDttm" in original_payload:
            payload["create_dttm"] = original_payload.get("createDttm")
        if "updateUserId" in original_payload:
            payload["update_user_id"] = original_payload.get("updateUserId")
        if "updateDttm" in original_payload:
            payload["update_dttm"] = original_payload.get("updateDttm")

        
        # branch_cnt, commit_cnt는 GitLab API에서 직접 제공하지 않으므로 None 또는 원본에서 가져오기
        if "branchCnt" in original_payload:
            payload["branch_cnt"] = original_payload.get("branchCnt")
        if "commitCnt" in original_payload:
            payload["commit_cnt"] = original_payload.get("commitCnt")
        
        # pms_info, plugins_info는 원본에서 가져오기
        if "pmsInfo" in original_payload:
            payload["pms_info"] = original_payload.get("pmsInfo")
        if "pluginsInfo" in original_payload:
            payload["plugins_info"] = original_payload.get("pluginsInfo")
        
        return payload