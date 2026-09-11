# Campus-AI frontend — only needed for an all-Railway deployment (Track B / --profile full).
# Track A (Vercel) does not need this file at all. See DEPLOYMENT.md for the full story.
#
#   docker build -t campus-ai-frontend --build-arg NEXT_PUBLIC_API_URL=https://your-api-domain -f Dockerfile .
#
# NEXT_PUBLIC_API_URL MUST be passed as a build arg, not just a runtime env var: Next.js inlines
# NEXT_PUBLIC_* variables into the browser bundle at build time. Setting it only at container
# start silently ships whatever (or nothing) was set at build time instead.
#
# Works without output: "standalone" in next.config.ts (copies node_modules wholesale -- larger
# image, but zero config changes required). Add output: "standalone" later as an optional size
# optimization if you want a smaller runtime image.

FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
EXPOSE 3000
CMD ["npm", "run", "start"]
