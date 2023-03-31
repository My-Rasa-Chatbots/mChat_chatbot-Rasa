build:
		bash builddockerimage.sh
up:
    docker compose up -d
down:
    docker compose down
show_logs:
    docker compose logs