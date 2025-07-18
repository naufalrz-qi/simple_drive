# Gunakan base image Python
FROM python:3.13.5

# Set working directory
WORKDIR /app

# Copy file ke container
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 80 di dalam container
EXPOSE 80

# Jalankan aplikasi Flask
CMD ["python", "app.py"]
