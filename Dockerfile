# Use Python 3.9 as base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/app:${PATH}"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    xvfb \
    libxi6 \
    libgconf-2-4 \
    default-jdk \
    curl \
    build-essential \
    libffi-dev \
    libssl-dev \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    libxss1 \
    libxtst6 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome WebDriver
RUN CHROME_DRIVER_VERSION=$(curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE) \
    && wget -q -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/${CHROME_DRIVER_VERSION}/chromedriver_linux64.zip \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin \
    && rm /tmp/chromedriver.zip \
    && chmod +x /usr/local/bin/chromedriver

# Install Microsoft Edge
RUN curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > microsoft.gpg \
    && install -o root -g root -m 644 microsoft.gpg /etc/apt/trusted.gpg.d/ \
    && sh -c 'echo "deb [arch=amd64] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge-dev.list' \
    && apt-get update \
    && apt-get install -y microsoft-edge-stable \
    && rm -rf /var/lib/apt/lists/*

# Install Edge WebDriver with fallback mechanism for version detection
RUN EDGE_VERSION=$(microsoft-edge --version | grep -oP "(?<=Microsoft Edge )[^[:space:]]+") \
    && EDGE_MAJOR_VERSION=$(echo $EDGE_VERSION | cut -d. -f1) \
    && wget -q -O /tmp/edgedriver.zip https://msedgedriver.azureedge.net/$EDGE_VERSION/edgedriver_linux64.zip \
    || wget -q -O /tmp/edgedriver.zip https://msedgedriver.azureedge.net/$EDGE_MAJOR_VERSION.0.0.0/edgedriver_linux64.zip \
    && unzip /tmp/edgedriver.zip -d /usr/local/bin \
    && rm /tmp/edgedriver.zip \
    && chmod +x /usr/local/bin/msedgedriver

# Install Firefox
RUN apt-get update && apt-get install -y firefox-esr \
    && rm -rf /var/lib/apt/lists/*

# Install Firefox GeckoDriver
RUN GECKO_DRIVER_VERSION=$(curl -sL https://api.github.com/repos/mozilla/geckodriver/releases/latest | grep tag_name | cut -d '"' -f 4) \
    && wget -q -O /tmp/geckodriver.tar.gz https://github.com/mozilla/geckodriver/releases/download/${GECKO_DRIVER_VERSION}/geckodriver-${GECKO_DRIVER_VERSION}-linux64.tar.gz \
    && tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin \
    && rm /tmp/geckodriver.tar.gz \
    && chmod +x /usr/local/bin/geckodriver

# Copy requirements file
COPY requirements.txt .

# Clean up requirements file (remove comments and fix format issues)
RUN sed -i 's/\/\/ filepath.*//g' requirements.txt && \
    sed -i '/^$/d' requirements.txt

# Install Python dependencies with specific versions
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt || true && \
    pip install --no-cache-dir flask==2.3.3 && \
    pip install --no-cache-dir Flask-RESTful==0.3.10 && \
    pip install --no-cache-dir Flask-Cors==4.0.0

# Fix specific package versions that might have failed
RUN pip install --no-cache-dir selenium==4.29.0 && \
    pip install --no-cache-dir undetected-chromedriver==3.5.5 && \
    pip install --no-cache-dir cryptography python-dotenv && \
    pip install --no-cache-dir dnspython==2.7.0 && \
    pip install --no-cache-dir py3dns

# Create threading2 workaround if needed
RUN mkdir -p /tmp/threading2_fix/threading2-0.3.1/threading2 && \
    cd /tmp/threading2_fix/threading2-0.3.1 && \
    echo 'import threading as _threading' > threading2/__init__.py && \
    echo 'Thread = _threading.Thread' >> threading2/__init__.py && \
    echo 'Lock = _threading.Lock' >> threading2/__init__.py && \
    echo 'RLock = _threading.RLock' >> threading2/__init__.py && \
    echo 'Condition = _threading.Condition' >> threading2/__init__.py && \
    echo 'Semaphore = _threading.Semaphore' >> threading2/__init__.py && \
    echo 'BoundedSemaphore = _threading.BoundedSemaphore' >> threading2/__init__.py && \
    echo 'Event = _threading.Event' >> threading2/__init__.py && \
    echo 'Timer = _threading.Timer' >> threading2/__init__.py && \
    echo 'from threading import *' >> threading2/__init__.py && \
    echo 'from setuptools import setup' > setup.py && \
    echo 'setup(' >> setup.py && \
    echo '    name="threading2",' >> setup.py && \
    echo '    version="0.3.1",' >> setup.py && \
    echo '    packages=["threading2"],' >> setup.py && \
    echo ')' >> setup.py && \
    pip install -e . && \
    cd / && \
    rm -rf /tmp/threading2_fix

# Create necessary directories
RUN mkdir -p /app/data /app/data/results /app/data/logs /app/data/temp /app/screenshots /app/terminal/files /app/results

# Create a script to start Xvfb and run any Python file
RUN echo '#!/bin/bash\nXvfb :99 -screen 0 1280x1024x24 &\nsleep 1\n\nif [ "$#" -eq 0 ]; then\n  python main.py\nelse\n  python "$@"\nfi' > /app/run.sh \
    && chmod +x /app/run.sh

# Set permissions
RUN chmod -R 755 /app

# Copy project files
COPY . /app/

# Expose port for the API
EXPOSE 5000

# Set entrypoint to the flexible run script
ENTRYPOINT ["/app/run.sh"]

# Default command (can be overridden)
CMD []
