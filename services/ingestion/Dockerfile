#Dockerfile container for ingestion service

#Image to work on
FROM python:3.11

#Create folder inside container for clarity
WORKDIR /ingestion-service

#Copy the code from the directory in the container
COPY . .

#Install dependencies ont he container
RUN pip install --no-cache-dir -r requirements.txt

#Run service main.py
CMD ["python", "main.py"]




