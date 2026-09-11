FROM node:20.18-alpine3.20 AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:20.18-alpine3.20
RUN apk add --no-cache tar git
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
