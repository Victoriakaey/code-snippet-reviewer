FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173
# Dev server; --host exposes it outside the container.
CMD ["npm", "run", "dev", "--", "--host"]
