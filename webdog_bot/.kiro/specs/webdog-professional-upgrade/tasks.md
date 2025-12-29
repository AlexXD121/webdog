# Implementation Plan

- [x] 1. Establish atomic database operations with concurrency safety, rolling backups, and storage guards
  - [x] Implement single-worker write queue to prevent race conditions during concurrent database access
  - [x] Add Write-Ahead Logging (WAL) with atomic file swapping and fsync operations for crash-safe writes
  - [x] Create pre-flight disk space validation to prevent silent failures from insufficient storage
  - [x] Implement rolling backup system with timestamped backups before any schema migration
  - [x] Add automatic rollback capability if migration fails with backup restoration
  - [x] Ensure all timestamps are stored in ISO 8601 UTC format for clock resilience across time zones
  - [x] Add database schema versioning system with migration support and validation
  - [x] Write comprehensive unit tests for atomic operations, concurrency safety, storage validation, and backup/restore functionality
  - _Requirements: 5.4, 6.2, 7.3_

- [x] 2. Implement enhanced data models with versioning support
  - [x] Extend JSON schema to include fingerprint versioning and forensic snapshots
  - [x] Create data classes for WeightedFingerprint, SimilarityMetrics, and ForensicSnapshot
  - [x] Implement schema migration logic for backward compatibility
  - [x] Add compressed snapshot storage using zlib compression
  - [x] Write unit tests for data model serialization and migration
  - _Requirements: 7.1, 7.2, 8.5_

- [x] 3. Build global request manager with de-duplication and hard timeouts
  - [x] Create GlobalRequestManager class with request collapsing functionality and resource leak prevention
  - [x] Implement strict 15-second hard timeouts using asyncio.wait_for to prevent zombie processes
  - [x] Add URL normalization for consistent de-duplication keys and request caching with 30-second TTL
  - [x] Create shared Future management for concurrent requests to same URL with proper cleanup
  - [x] Implement timeout exception handling and task cancellation for failed requests
  - [x] Write unit tests for request de-duplication, timeout behavior, and resource cleanup
  - _Requirements: 6.1, 6.3, 3.5_

- [x] 4. Develop versioned content fingerprinting system with block-page detection
  - [x] Create VersionedContentFingerprinter class with algorithm versioning and anti-block validation
  - [x] Implement structure-aware content extraction with semantic weights and bot-blocking page detection
  - [x] Add noise filtering for timestamps, session IDs, and dynamic content with block-page indicators
  - [x] Create weighted fingerprint generation with content importance scoring and block validation
  - [x] Implement silent baseline reset for fingerprint version migrations without false alerts
  - [x] Add block-page detection for common bot-blocking strings (Cloudflare, DDoS-Guard, Captcha)
  - [x] Write unit tests for content extraction, fingerprint versioning, and block-page detection accuracy
  - _Requirements: 2.1, 2.5, 8.1, 3.2_

- [x] 5. Implement multi-algorithm similarity detection
  - [x] Create comprehensive similarity calculation using Jaccard Index and Levenshtein distance
  - [x] Add semantic structure comparison for content analysis
  - [x] Implement weighted scoring system combining multiple similarity metrics
  - [x] Create change type classification (UI_TWEAK, CONTENT_UPDATE, MAJOR_OVERHAUL)
  - [x] Write unit tests with known similarity test cases and expected outcomes
  - _Requirements: 2.2, 2.3, 2.4_

- [ ] 6. Build forensic change detection with Telegram payload safety
  - Extend ChangeDetector to create compressed forensic snapshots with safe diff generation
  - Implement Telegram payload safety with 3000-character diff truncation and summary generation
  - Add forensic replay functionality for dispute resolution with compressed snapshot storage
  - Create safe markdown diff generation that prevents Telegram API errors from oversized messages
  - Implement diff summary generation for truncated content with line count statistics
  - Limit forensic snapshots to last 3 changes per URL for storage efficiency
  - Write unit tests for snapshot creation, compression, replay, and Telegram safety limits
  - _Requirements: 7.1, 7.2, 4.4_

- [ ] 7. Implement circuit breaker pattern for resilient web fetching
  - Create CircuitBreaker class with configurable failure thresholds
  - Add state management (CLOSED, OPEN, HALF_OPEN) with recovery timeouts
  - Implement failure counting and automatic recovery logic
  - Integrate circuit breaker with website fetching operations
  - Add circuit breaker state monitoring and reporting
  - Write unit tests for circuit breaker state transitions and recovery
  - _Requirements: 3.2, 3.4, 5.2_

- [ ] 8. Develop anti-bot header rotation and spoofing system
  - Create realistic browser signature pool with User-Agent rotation
  - Implement comprehensive header spoofing (Sec-Ch-Ua, Accept, Accept-Language)
  - Add cookie handling for session-locked websites
  - Create randomized request timing with 1-5 second intervals
  - Implement robots.txt respect and ethical scraping practices
  - Write unit tests for header rotation and timing randomization
  - _Requirements: 3.1, 3.3, 3.5_

- [ ] 9. Build structured logging system with correlation IDs
  - Create StructuredLogger class with JSON-formatted output
  - Implement correlation ID tracking using chat_id for cross-component debugging
  - Add comprehensive error context including stack traces and system metrics
  - Create log aggregation for error patterns and system health monitoring
  - Implement log rotation and retention policies
  - Write unit tests for log formatting and correlation ID propagation
  - _Requirements: 5.1, 5.5_

- [ ] 10. Implement health monitoring and metrics collection
  - Create system health metrics collection (response times, success rates, worker saturation)
  - Add per-user statistics tracking and reporting
  - Implement health endpoint or admin command for system status
  - Create alerting for critical system metrics and thresholds
  - Add performance monitoring for database operations and web requests
  - Write unit tests for metrics collection and health status reporting
  - _Requirements: 5.1, 6.4_

- [ ] 11. Develop enhanced Telegram interface with inline keyboards
  - Create inline keyboard layouts for main actions (Add Site, List Sites, Settings, Health)
  - Implement smart snooze functionality with 1h, 6h, 24h options
  - Add visual diff display in change notifications with markdown formatting
  - Create pagination for monitor lists when users have >10 websites
  - Implement bulk operations interface with checkbox selections
  - Write unit tests for keyboard generation and callback handling
  - _Requirements: 4.1, 4.2, 4.3, 4.5, 1.4_

- [ ] 12. Build user configuration and customization system
  - Create user settings management for similarity thresholds and check intervals
  - Implement notification preferences (alert types, timing, formatting)
  - Add per-website configuration options and expert mode settings
  - Create settings validation with immediate feedback on invalid configurations
  - Implement settings persistence and migration for schema changes
  - Write unit tests for settings validation and persistence
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 13. Implement rate limiting and API compliance
  - Create global RPS (Requests Per Second) governor for ethical scraping
  - Implement Telegram API rate limiting (30 messages per second compliance)
  - Add adaptive monitoring intervals based on system load
  - Create request queuing and throttling mechanisms
  - Implement backpressure handling when rate limits are exceeded
  - Write unit tests for rate limiting behavior and queue management
  - _Requirements: 6.1, 6.3, 6.4_

- [ ] 14. Develop change history and data export functionality
  - Implement 30-day change history storage with metadata
  - Create change history retrieval and display functionality
  - Add data export capabilities in JSON and CSV formats
  - Implement automatic data archiving when storage limits are reached
  - Create data compression strategies for efficient storage usage
  - Write unit tests for history management and export functionality
  - _Requirements: 7.1, 7.2, 7.4, 7.5_

- [ ] 15. Integrate all components with memory-optimized main controller
  - Update main.py to implement job-based loading instead of loading entire database into memory
  - Create JobBasedDataLoader for lightweight metadata caching and on-demand full config loading
  - Implement proper dependency injection and component lifecycle management with resource cleanup
  - Add graceful shutdown handling with proper async task cancellation and write queue draining
  - Implement system startup validation and component health checks with failure recovery
  - Create memory usage monitoring and optimization for large-scale deployments
  - Write integration tests for complete monitoring workflows and memory usage patterns
  - _Requirements: 1.1, 1.2, 1.3, 5.3, 6.2_

- [ ] 16. Create comprehensive test suite and validation
  - Develop end-to-end test scenarios covering complete monitoring cycles
  - Create performance tests for concurrent monitoring with 1000+ websites
  - Implement chaos testing for database corruption and network failures
  - Add load testing for Telegram API integration and rate limiting
  - Create test fixtures for algorithm validation with known inputs/outputs
  - Write documentation and deployment guides for production usage
  - _Requirements: 6.1, 6.2, 5.4_