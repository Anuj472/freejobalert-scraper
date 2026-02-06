# Contributing to FreeJobAlert Scraper

Thank you for considering contributing to this project! We welcome contributions from the community.

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:
- Clear description of the bug
- Steps to reproduce
- Expected vs actual behavior
- Your environment (OS, Python version, etc.)
- Relevant logs or screenshots

### Suggesting Enhancements

For feature requests:
- Clearly describe the feature
- Explain why it would be useful
- Provide examples of how it would work

### Code Contributions

1. **Fork the repository**
   ```bash
   git clone https://github.com/Anuj472/freejobalert-scraper.git
   cd freejobalert-scraper
   ```

2. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Set up development environment**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   source venv/bin/activate
   ```

4. **Make your changes**
   - Write clean, readable code
   - Follow Python PEP 8 style guide
   - Add comments for complex logic
   - Update documentation if needed

5. **Test your changes**
   ```bash
   python test_connection.py
   python main.py --max-pages 1  # Test with limited scraping
   ```

6. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add your feature description"
   ```

   Use conventional commit messages:
   - `feat:` for new features
   - `fix:` for bug fixes
   - `docs:` for documentation changes
   - `refactor:` for code refactoring
   - `test:` for adding tests
   - `chore:` for maintenance tasks

7. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

8. **Create a Pull Request**
   - Go to the original repository
   - Click "New Pull Request"
   - Select your branch
   - Describe your changes clearly
   - Link any related issues

## Code Style Guidelines

### Python Code
- Follow PEP 8 style guide
- Use type hints where appropriate
- Maximum line length: 100 characters
- Use docstrings for functions and classes

### Example:
```python
def extract_job_data(self, card: BeautifulSoup, category: str) -> Optional[Dict[str, Any]]:
    """Extract job data from a job card element.
    
    Args:
        card: BeautifulSoup element containing job information
        category: Job category string
    
    Returns:
        Dictionary containing job data or None if extraction fails
    """
    # Implementation
```

### Logging
- Use appropriate log levels:
  - `DEBUG`: Detailed diagnostic information
  - `INFO`: General informational messages
  - `WARNING`: Warning messages
  - `ERROR`: Error messages
- Include context in log messages

### Error Handling
- Use specific exception types
- Always log errors with context
- Fail gracefully when possible

## Testing

Before submitting:
1. Run connection tests: `python test_connection.py`
2. Test scraping with limited pages: `python main.py --max-pages 1`
3. Check logs for errors: `tail -f scraper.log`
4. Verify data is correctly stored in Supabase
5. Confirm PDFs are uploaded to Google Drive

## Documentation

Update documentation when:
- Adding new features
- Changing configuration options
- Modifying API endpoints
- Updating dependencies

Documentation files to update:
- `README.md` - Main documentation
- `CONTRIBUTING.md` - This file
- Code docstrings
- Configuration examples

## Areas for Contribution

We especially welcome contributions in:

### High Priority
- [ ] Improved HTML parsing for different job page layouts
- [ ] Better date extraction and parsing
- [ ] Enhanced PDF detection algorithms
- [ ] Rate limiting and request throttling
- [ ] Retry logic improvements

### Medium Priority
- [ ] Email notification system
- [ ] Keyword-based job filtering
- [ ] Web dashboard for viewing jobs
- [ ] Support for additional job portals
- [ ] Job deduplication logic

### Nice to Have
- [ ] Telegram/WhatsApp notifications
- [ ] Advanced search and filtering
- [ ] Job recommendation engine
- [ ] Mobile app integration
- [ ] Analytics and reporting

## Code Review Process

1. A maintainer will review your PR
2. Changes may be requested
3. Once approved, your PR will be merged
4. Your contribution will be acknowledged

## Questions?

Feel free to:
- Open an issue for questions
- Start a discussion
- Contact maintainers

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Recognition

All contributors will be acknowledged in the project. Significant contributions may earn you co-maintainer status.

Thank you for contributing! 🎉