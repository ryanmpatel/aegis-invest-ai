FROM node:22-alpine AS builder
WORKDIR /srv/app
COPY package.json package-lock.json* ./
RUN npm install --no-fund --no-audit
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine
WORKDIR /srv/app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /srv/app/.next/standalone ./
COPY --from=builder /srv/app/.next/static ./.next/static
COPY --from=builder /srv/app/public ./public
EXPOSE 3000
ENV BACKEND_INTERNAL_URL=http://backend:8000
CMD ["node", "server.js"]
