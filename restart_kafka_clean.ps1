
# Stop containers
docker-compose -f k8-setup/kafka.yml down -v

# Remove any lingering containers
docker rm -f kafka zookeeper schema-registry control-center kafka-rest 2>nul

# Start up again
docker-compose -f k8-setup/kafka.yml up -d
