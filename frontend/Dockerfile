# File: frontend/Dockerfile

# Stage 1: Build React/Vite
FROM node:20-alpine as builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install
COPY . .
# Build production code
RUN npm run build

# Stage 2: Serve dengan Nginx (Ringan & Cepat)
FROM nginx:alpine
# Copy hasil build dari Stage 1 ke folder Nginx
COPY --from=builder /app/dist /usr/share/nginx/html
# Config default Nginx
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]