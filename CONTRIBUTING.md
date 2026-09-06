# Contributing to PRAHARI

Thank you for your interest in contributing to PRAHARI. This document provides guidelines and instructions for contributing.

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive feedback
- Respect differing viewpoints and experiences

## How to Contribute

### Reporting Bugs

1. Check existing issues to avoid duplicates
2. Use the bug report template
3. Include steps to reproduce, expected behavior, and environment details

### Suggesting Features

1. Check existing feature requests
2. Use the feature request template
3. Describe the problem, proposed solution, and alternatives

### Code Contributions

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes following the coding standards below
4. Run tests: `pytest tests/` and `cd dashboard && npx tsc --noEmit`
5. Commit with a clear message: `git commit -m 'Add amazing feature'`
6. Push to your fork: `git push origin feature/amazing-feature`
7. Open a Pull Request using the PR template

## Coding Standards

### Python
- Follow PEP 8
- Use type hints for all public functions
- Write docstrings for modules, classes, and public methods
- Use Black for formatting
- Use isort for import organization

### TypeScript/React
- Use functional components with hooks
- Define explicit prop types/interfaces
- Use TailwindCSS for styling
- Follow React best practices

## Project Structure

```
prahari/
├── services/           # Python microservices
├── shared/             # Canonical schema + base classes
├── dashboard/          # React frontend
├── scripts/            # Operational scripts
├── tests/              # Test suite
├── docs/               # Documentation
└── config/             # Configuration files
```

## Questions?

Feel free to open an issue for any questions about contributing.

**Maintainer:** Sumit Nawale  
**LinkedIn:** https://www.linkedin.com/in/sumit-nawale-25274638b