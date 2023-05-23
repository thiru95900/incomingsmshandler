# Base image
FROM python:3.7

# Set the working directory
WORKDIR /IncomingSmsHandler

# Copy the source code and requirements into the container
COPY . /IncomingSmsHandler

#install dependencies packages
ENV C_FORCE_ROOT=1

#install supervisor
RUN apt-get update && apt-get install -y supervisor

# COPY app conf into supervisord path
COPY supervisor/integration/incoming_sms_handler.conf /etc/supervisor/conf.d/incoming_sms_handler.conf

#Install some more dependencies.
RUN pip install --upgrade wheel

#create virt env
WORKDIR /IncomingSmsHandler
RUN mkdir -p /IncomingSmsHandler/virt/incoming_handler3/ && \
python3 -m venv /IncomingSmsHandler/virt/incoming_handler3/

#Virt env activate and install requerements.txt
RUN . /IncomingSmsHandler/virt/incoming_handler3/bin/activate && \
pip install -r requirements.txt


#create log file stored
RUN mkdir -p /home/usher/logs/IncomingSMSHandler/
RUN mkdir -p /extra-01/logs/IncomingSMSHandler/


#start supervisor
CMD ["/usr/bin/supervisord", "-n"]

