# DrumScribe Documentation

This directory contains technical documentation for DrumScribe.

## 📚 Documentation Index

### Operations & Deployment

**[DEVOPS.md](DEVOPS.md)** - Production Operations Manual
- Deployment strategies (Railway, Fly.io, Hetzner)
- Scaling guidelines and resource requirements
- Model pre-seeding and caching strategies
- OOM analysis and memory optimization
- Disaster recovery and backup procedures
- Monitoring and observability setup

### Machine Learning

**[ML_PIPELINE.md](ML_PIPELINE.md)** - ML Pipeline Architecture
- Demucs source separation configuration
- CNN architecture and hit classification
- BPM detection strategy (madmom + librosa)
- music21 transcription workflow
- Model lifecycle and caching
- Performance optimization

### Deployment Modes

**[MVP_MODE.md](MVP_MODE.md)** - MVP Deployment Guide
- Running without Celery/Redis (simplified mode)
- In-process ML pipeline execution
- Resource requirements for MVP
- When to use MVP vs full stack
- Migration path from MVP to production

## 🚀 Quick Links

- **Getting Started**: See [root README.md](../README.md)
- **API Reference**: See [backend/README.md](../backend/README.md)
- **Frontend Guide**: See [frontend/README.md](../frontend/README.md)
- **Scripts & Orchestration**: See [scripts/README.md](../scripts/README.md)

## 📖 Additional Resources

### Architecture Diagrams

The main [README.md](../README.md) contains:
- System architecture (Mermaid diagram)
- Tech stack overview
- Project structure

### Development Guides

- **Backend**: [backend/README.md](../backend/README.md) - API development, testing, local setup
- **Frontend**: [frontend/README.md](../frontend/README.md) - Component structure, hooks, testing
- **Scripts**: [scripts/README.md](../scripts/README.md) - Orchestration, health checks, debugging

## 🔧 Configuration

All configuration is managed via the root `.env` file. See [.env.example](../.env.example) for available options.

Key configuration areas:
- Model management (MODEL_URI, MODEL_VERSION, MODEL_SHA256)
- Storage backend (local vs S3)
- PDF export backend (LilyPond vs MuseScore)
- Resource limits and concurrency
- Observability and monitoring

## 📝 Contributing

When adding new documentation:

1. Keep it focused and technical
2. Include code examples where relevant
3. Update this index when adding new docs
4. Use Mermaid for diagrams
5. Link to related documentation
