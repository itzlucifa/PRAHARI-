FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
COPY index.html .
COPY src ./src
COPY tsconfig.json .
COPY vite.config.ts .
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm install
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
