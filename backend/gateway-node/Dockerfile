FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev

# Run ./predeploy.sh first (vendors ./widget/translation-widget.js) so this
# COPY picks it up — see predeploy.sh for why.
COPY . .

ENV PORT=8787
EXPOSE 8787

CMD ["node", "server.js"]
