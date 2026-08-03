FROM node:20-alpine
WORKDIR /app
COPY package.json ./
COPY src/frontend/package.json ./src/frontend/package.json
RUN npm install
COPY src/frontend ./src/frontend
EXPOSE 5173
CMD ["npm", "run", "frontend:dev", "--", "--host", "0.0.0.0"]
