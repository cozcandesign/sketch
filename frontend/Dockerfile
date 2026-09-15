# Aşama 1: Vite build
FROM node:22-alpine AS build
ARG VITE_GIT_SHA=bilinmiyor
ENV VITE_GIT_SHA=$VITE_GIT_SHA
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Aşama 2: nginx statik servis + /api ve /ws proxy
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
