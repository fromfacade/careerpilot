# Frontend dev container for docker-compose (CI / non-Windows dev parity).
#
# NOTE: not run on the primary dev machine for this project (no Docker
# Desktop there). Runs the Vite dev server rather than a production build,
# matching how the backend container is used for local iteration.
FROM node:22-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
