# syntax=docker/dockerfile:1.7
FROM node:20-bullseye

WORKDIR /app

ENV PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH

RUN corepack enable pnpm

COPY package.json pnpm-workspace.yaml tsconfig.base.json ./
COPY packages/web-ui/package.json packages/web-ui/
COPY packages/web-ui/tsconfig.json packages/web-ui/
COPY packages/web-ui/vite.config.ts packages/web-ui/
COPY packages/web-ui/index.html packages/web-ui/
COPY packages/web-ui/src packages/web-ui/src
COPY packages/web-ui/styles.css packages/web-ui/
COPY packages/web-ui/.env.example packages/web-ui/

RUN pnpm install --frozen-lockfile --prefer-offline || pnpm install --prefer-offline

EXPOSE 5173
CMD ["pnpm", "--filter", "@motosub/web-ui", "dev", "--host", "0.0.0.0", "--port", "5173"]
