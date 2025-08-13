# Stage 1: Build the React app with Node 20 LTS
FROM node:20.14.0-alpine AS builder
WORKDIR /app
COPY package.json .
RUN yarn install --frozen-lockfile
COPY . .
RUN yarn build

# Stage 2: Serve the static files with Nginx 1.26
FROM nginx:1.26-alpine
COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
