import logging
from typing import Dict, Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class GitLabClient:
    def __init__(self, base_url: str, token: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        
        # 세션 생성 및 재시도 전략 설정
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # 기본 헤더 설정
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        })
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """HTTP 요청 헬퍼 메서드"""
        url = f"{self.base_url}/api/v4{endpoint}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.exceptions.RequestException as e:
            logger.error(f"GitLab API request failed: {method} {url}, error: {e}")
            raise
    
    def fork_project(
        self,
        project_id: int,
        namespace_id: Optional[int] = None,
        name: Optional[str] = None,
        path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        프로젝트를 fork하여 새 프로젝트 생성
        
        Args:
            project_id: Fork할 원본 프로젝트 ID
            namespace_id: Fork된 프로젝트가 생성될 namespace ID 
            name: Fork된 프로젝트의 이름 (선택)
            path: Fork된 프로젝트의 path (선택)
        
        Returns:
            생성된 프로젝트 정보
        """
        json_data = {}
        if namespace_id:
            json_data["namespace_id"] = namespace_id
        if name:
            json_data["name"] = name
        if path:
            json_data["path"] = path
        
        logger.info(f"Forking project {project_id} with params: {json_data}")
        result = self._request("POST", f"/projects/{project_id}/fork", json_data=json_data)
        forked_project_id = result.get('id')
        logger.info(f"Project forked successfully: {forked_project_id}")
        
        # 1. Fork relationship 삭제
        try:
            self.delete_fork_relationship(forked_project_id)
            logger.info(f"Fork relationship deleted for project {forked_project_id}")
        except Exception as e:
            logger.warning(f"Failed to delete fork relationship for project {forked_project_id}: {e}")
        
        # 2. test, main 브랜치를 maintainer 권한으로 protected branch 설정
        for branch_name in ['test', 'main']:
            try:
                self.protect_branch(forked_project_id, branch_name)
                logger.info(f"Branch {branch_name} protected for project {forked_project_id}")
            except Exception as e:
                logger.warning(f"Failed to protect branch {branch_name} for project {forked_project_id}: {e}")
        
        return result
    
    def add_project_member(
        self,
        project_id: int,
        user_id: int,
        access_level: int = 30
    ) -> Dict[str, Any]:
        """
        프로젝트에 사용자 추가
        
        Args:
            project_id: 프로젝트 ID
            user_id: 추가할 사용자 ID
            access_level: 접근 레벨 (10=Guest, 20=Reporter, 30=Developer, 40=Maintainer, 50=Owner)
        
        Returns:
            추가된 멤버 정보
        """
        json_data = {
            "user_id": user_id,
            "access_level": access_level
        }
        
        logger.info(
            f"Adding user {user_id} to project {project_id} "
            f"with access level {access_level}"
        )
        result = self._request(
            "POST",
            f"/projects/{project_id}/members",
            json_data=json_data
        )
        logger.info(f"User added to project successfully: {result.get('id')}")
        return result
    
    def get_project(self, project_id: int) -> Dict[str, Any]:
        """프로젝트 정보 조회"""
        return self._request("GET", f"/projects/{project_id}")
    
    def get_user(self, user_id: int) -> Dict[str, Any]:
        """사용자 정보 조회"""
        return self._request("GET", f"/users/{user_id}")
    
    def delete_fork_relationship(self, project_id: int) -> None:
        """
        프로젝트의 fork relationship 삭제
        
        Args:
            project_id: Fork relationship을 삭제할 프로젝트 ID
        """
        logger.info(f"Deleting fork relationship for project {project_id}")
        self._request("DELETE", f"/projects/{project_id}/fork")
        logger.info(f"Fork relationship deleted successfully for project {project_id}")
    
    def protect_branch(
        self,
        project_id: int,
        branch_name: str,
        push_access_level: int = 40,
        merge_access_level: int = 40
    ) -> Dict[str, Any]:
        """
        브랜치를 protected branch로 설정
        
        Args:
            project_id: 프로젝트 ID
            branch_name: 보호할 브랜치 이름 (test, main 등)
            push_access_level: Push 권한 레벨 (40=Maintainer)
            merge_access_level: Merge 권한 레벨 (40=Maintainer)
        
        Returns:
            Protected branch 설정 정보
        """
        json_data = {
            "name": branch_name,
            "push_access_levels": [{"access_level": push_access_level}],
            "merge_access_levels": [{"access_level": merge_access_level}]
        }
        
        logger.info(
            f"Protecting branch {branch_name} for project {project_id} "
            f"with push_access_level={push_access_level}, merge_access_level={merge_access_level}"
        )
        result = self._request(
            "POST",
            f"/projects/{project_id}/protected_branches",
            json_data=json_data
        )
        logger.info(f"Branch {branch_name} protected successfully for project {project_id}")
        return result