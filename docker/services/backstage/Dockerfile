FROM node:24-bookworm-slim AS builder

ENV PYTHON=/usr/bin/python3
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 g++ build-essential libsqlite3-dev && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g yarn@1

WORKDIR /app
COPY backstage/.yarn ./.yarn
COPY backstage/.yarnrc.yml backstage/yarn.lock backstage/package.json backstage/backstage.json ./
COPY backstage/packages/app/package.json ./packages/app/package.json
COPY backstage/packages/backend/package.json ./packages/backend/package.json
COPY backstage/plugins ./plugins
RUN yarn install --frozen-lockfile

COPY backstage/packages ./packages
COPY backstage/app-config.yaml backstage/tsconfig.json ./
COPY docs/backstage ./docs/backstage

RUN yarn tsc
RUN yarn build:backend --config app-config.yaml
RUN yarn workspace app build

# ---- production image ----
FROM node:24-bookworm-slim

ENV PYTHON=/usr/bin/python3 NODE_ENV=production NODE_OPTIONS="--no-node-snapshot"

RUN apt-get update && \
    apt-get install -y --no-install-recommends python3 g++ build-essential libsqlite3-dev curl && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g yarn@1

USER node
WORKDIR /app

COPY --from=builder --chown=node:node /app/.yarn ./.yarn
COPY --from=builder --chown=node:node /app/.yarnrc.yml /app/yarn.lock /app/package.json /app/backstage.json ./
COPY --from=builder --chown=node:node /app/packages/backend/dist/skeleton.tar.gz ./
RUN tar xzf skeleton.tar.gz && rm skeleton.tar.gz
RUN --mount=type=cache,target=/home/node/.cache/yarn,sharing=locked,uid=1000,gid=1000 \
    yarn workspaces focus --all --production

COPY --from=builder --chown=node:node /app/packages/backend/dist/bundle.tar.gz ./
RUN tar xzf bundle.tar.gz && rm bundle.tar.gz

COPY --from=builder --chown=node:node /app/app-config.yaml ./
COPY --from=builder --chown=node:node /app/docs ./docs

CMD ["node", "packages/backend", "--config", "app-config.yaml"]
