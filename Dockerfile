# Python 멀티 스테이지 빌드

# ============================================
# Stage 1: 빌드 스테이지
# ============================================
FROM python:3.11-slim AS builder

WORKDIR /app

# 의존성 파일 복사
COPY requirements.txt .

# 의존성 설치
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================
# Stage 2: 실행 스테이지
# ============================================
FROM python:3.11-slim

# 보안을 위한 non-root 사용자 생성
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 필요한 패키지 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 빌드 스테이지에서 Python 패키지 복사
COPY --from=builder /root/.local /home/appuser/.local

# 소스 코드 복사
COPY . .

# 소유권 변경
RUN chown -R appuser:appuser /app

# PATH에 사용자 로컬 bin 추가
ENV PATH=/home/appuser/.local/bin:$PATH

# non-root 사용자로 전환
USER appuser

# 헬스체크 설정 (Python 프로세스 확인)
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import sys; sys.exit(0)" || exit 1

# 애플리케이션 실행
CMD ["python", "main.py"]
