#!/bin/bash

# AutoPR Deployment Script for Fly.io
set -e

echo "🚀 Deploying AutoPR to Fly.io..."

# Check if flyctl is installed
if ! command -v flyctl &> /dev/null; then
    echo "❌ flyctl is not installed. Please install it first:"
    echo "curl -L https://fly.io/install.sh | sh"
    exit 1
fi

# Check if logged in
if ! flyctl auth whoami &> /dev/null; then
    echo "❌ Please log in to Fly.io first:"
    echo "flyctl auth login"
    exit 1
fi

# Check required environment variables
if [ -z "$GROQ_API_KEY" ]; then
    echo "❌ GROQ_API_KEY environment variable is required"
    echo "Set it with: export GROQ_API_KEY=your_key_here"
    exit 1
fi

# Create or update the app
if flyctl apps list | grep -q "autopr-backend"; then
    echo "📱 App exists, updating..."
else
    echo "📱 Creating new app..."
    flyctl apps create autopr-backend --org personal
fi

# Set secrets
echo "🔒 Setting secrets..."
flyctl secrets set GROQ_API_KEY="$GROQ_API_KEY" --app autopr-backend

if [ ! -z "$GITHUB_TOKEN" ]; then
    flyctl secrets set GITHUB_TOKEN="$GITHUB_TOKEN" --app autopr-backend
    echo "✅ GitHub token set"
else
    echo "⚠️  GITHUB_TOKEN not set - you can set it later with:"
    echo "flyctl secrets set GITHUB_TOKEN=your_token_here --app autopr-backend"
fi

# Deploy
echo "🏗️  Deploying..."
flyctl deploy --app autopr-backend

# Show app info
echo "✅ Deployment complete!"
echo "🌐 Your app is available at: https://autopr-backend.fly.dev"
echo "🔍 Health check: https://autopr-backend.fly.dev/health"
echo ""
echo "📊 View logs: flyctl logs --app autopr-backend"
echo "📈 Monitor: flyctl status --app autopr-backend"