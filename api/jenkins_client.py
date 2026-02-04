import logging
from typing import Dict, Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class JenkinsClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
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
        
        # Basic 인증 설정 (requests가 자동으로 헤더 생성)
        self.session.auth = (username, password)
    
    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """HTTP 요청 헬퍼 메서드"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                data=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            # Jenkins API는 일부 엔드포인트에서 빈 응답을 반환할 수 있음
            if response.content:
                try:
                    return response.json()
                except ValueError:
                    # JSON이 아닌 경우 텍스트 반환
                    return {"content": response.text}
            return {}
        except requests.exceptions.RequestException as e:
            logger.error(f"Jenkins API request failed: {method} {url}, error: {e}")
            raise
    
    def _build_folder_endpoint(self, folder_path: str) -> str:
        """
        폴더 경로를 Jenkins API 엔드포인트 형식으로 변환
        
        Args:
            folder_path: 폴더 경로 (예: "/new/era/" 또는 "new/era/")
        
        Returns:
            Jenkins API 엔드포인트 (예: "/job/new/job/era")
        """
        # 앞뒤 슬래시 제거 및 빈 문자열 처리
        path = folder_path.strip('/')
        if not path:
            return ""
        
        # 각 폴더를 /job/로 연결
        folders = [f for f in path.split('/') if f]
        endpoint = '/'.join([f"job/{folder}" for folder in folders])
        
        return f"/{endpoint}" if endpoint else ""
    
    def copy_project(
        self,
        source_job_name: str,
        target_folder_path: str,
        new_job_name: str
    ) -> Dict[str, Any]:
        """
        다른 폴더의 프로젝트를 복사하여 새 프로젝트 생성
        
        Args:
            source_job_name: 복사할 원본 프로젝트 경로 (예: "/a/b/template" 또는 "a/b/template")
            target_folder_path: 생성할 폴더 경로 (예: "/new/era/" 또는 "new/era/")
            new_job_name: 생성할 새 프로젝트 이름 (예: "new-era-project")
        
        Returns:
            생성된 프로젝트 정보
        """
        # source_job_name에서 앞의 슬래시 제거
        source_path = source_job_name.lstrip('/')
        
        # 폴더 경로를 Jenkins API 엔드포인트 형식으로 변환
        folder_endpoint = self._build_folder_endpoint(target_folder_path)
        
        # 엔드포인트 구성: /job/new/job/era/createItem
        endpoint = f"{folder_endpoint}/createItem" if folder_endpoint else "/createItem"
        
        # Jenkins API는 form-urlencoded 형식 사용
        # URL 파라미터로 전달
        params = {
            "name": new_job_name,
            "mode": "copy",
            "from": source_path
        }
        
        logger.info(
            f"Copying Jenkins project from '{source_job_name}' to "
            f"'{target_folder_path}{new_job_name}'"
        )
        
        try:
            response = self.session.post(
                f"{self.base_url}{endpoint}",
                params=params,
                timeout=self.timeout,
                allow_redirects=False
            )
            
            # Jenkins는 200 또는 302 리다이렉트로 성공을 나타냄
            if response.status_code in [200, 302]:
                # 최종 경로 구성
                final_path = f"{target_folder_path.rstrip('/')}/{new_job_name}".lstrip('/')
                logger.info(
                    f"Jenkins project copied successfully: "
                    f"source='{source_job_name}', new='{final_path}'"
                )
                # 새 프로젝트 정보 조회
                return self.get_project(final_path)
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Failed to copy Jenkins project: "
                f"source='{source_job_name}', target_folder='{target_folder_path}', "
                f"new_job='{new_job_name}', error={e}"
            )
            raise
    
    def get_project(self, job_path: str) -> Dict[str, Any]:
        """
        프로젝트 정보 조회
        
        Args:
            job_path: 프로젝트 경로 (예: "new/era/new-era-project" 또는 "/new/era/new-era-project")
        
        Returns:
            프로젝트 정보
        """
        # 앞의 슬래시 제거
        path = job_path.lstrip('/')
        
        # 각 경로 요소를 /job/로 연결
        # 예: "new/era/new-era-project" -> "/job/new/job/era/job/new-era-project"
        parts = [f for f in path.split('/') if f]
        endpoint = '/'.join([f"job/{part}" for part in parts])
        endpoint = f"/{endpoint}/api/json"
        
        logger.info(f"Getting Jenkins project info: {job_path}")
        result = self._request("GET", endpoint)
        logger.info(f"Jenkins project info retrieved: {job_path}")
        return result
    
    def project_exists(self, job_name: str) -> bool:
        """
        프로젝트 존재 여부 확인
        
        Args:
            job_name: 프로젝트 이름
        
        Returns:
            존재 여부
        """
        try:
            self.get_project(job_name)
            return True
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return False
            raise
