#Dockerfile container for extraction service

#Image to work on
FROM python:3.11

#Create folder inside container for clarity
WORKDIR /extraction-service

#Copy the code from the directory in the container
COPY . .

#Install dependencies on the container
RUN pip install --no-cache-dir -r requirements.txt

#Run service main.py
CMD ["python", "main.py"]
