FROM ubuntu:22.04

# 비대화형 환경으로 설정 (설치 중 사용자 입력 대기 방지)
ENV DEBIAN_FRONTEND=noninteractive

# XFCE 데스크톱, VNC, noVNC, 크로미움 브라우저 및 한글 폰트(fonts-nanum) 설치
RUN apt-get update && apt-get install -y \
    xfce4 \
    xfce4-terminal \
    tigervnc-standalone-server \
    novnc \
    websockify \
    chromium-browser \
    curl \
    wget \
    git \
    sudo \
    dbus-x11 \
    fonts-nanum \
    libnss3 \
    libnspr4 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# VNC 접속 시 비밀번호 없이 바로 화면에 진입하도록 설정
RUN mkdir -p /root/.vnc && echo "SecurityTypes=None" > /root/.vnc/config

# VNC 서버와 noVNC(웹 변환 프록시)를 구동하는 시작 스크립트
RUN echo '#!/bin/bash\n\
export USER=root\n\
export DISPLAY=:1\n\
# 기존에 남아있을 수 있는 VNC 세션 및 락(lock) 파일 정리\n\
vncserver -kill :1 2>/dev/null || true\n\
rm -rf /tmp/.X1-lock /tmp/.X11-unix/X1\n\
# VNC 서버 시작 (1280x800 해상도)\n\
vncserver :1 -geometry 1280x800 -depth 24 -xstartup startxfce4\n\
# noVNC 서비스 실행 (6080 포트를 통해 VNC를 웹으로 연결)\n\
pkill websockify 2>/dev/null || true\n\
nohup websockify --web /usr/share/novnc 6080 localhost:5901 > /var/log/novnc.log 2>&1 &\n\
' > /usr/local/bin/start-vnc.sh && \
    chmod +x /usr/local/bin/start-vnc.sh
