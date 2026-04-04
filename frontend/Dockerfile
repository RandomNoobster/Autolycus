FROM node:20-alpine AS build

WORKDIR /app

COPY frontend/package*.json /app/

RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend /app

ARG VITE_API_URL
ARG VITE_AUTH_TOKEN_API_KEY
ARG VITE_SITE_ORIGIN

ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_AUTH_TOKEN_API_KEY=${VITE_AUTH_TOKEN_API_KEY}
ENV VITE_SITE_ORIGIN=${VITE_SITE_ORIGIN}

RUN npm run build

FROM nginx:alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
