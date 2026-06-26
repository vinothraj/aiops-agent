# Step 1: Build the Angular Application
FROM node:20-alpine AS build

WORKDIR /app

# Copy package descriptors
COPY package*.json /app/

# Install dependencies with legacy-peer-deps to avoid conflict resolution blocks
RUN npm ci --legacy-peer-deps

# Copy application source code
COPY . /app/

# Build application
RUN npm run build -- --configuration=production

# Step 2: Serve the application using Nginx
FROM nginx:alpine

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy build artifacts from browser folder to Nginx html directory
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
