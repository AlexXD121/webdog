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

- [x] 6. Build forensic change detection with Telegram payload safety
  - [x] Extend ChangeDetector to create compressed forensic snapshots with safe diff generation
  - [x] Implement Telegram payload safety with 3000-character diff truncation and summary generation
  - [x] Add forensic replay functionality for dispute resolution with compressed snapshot storage
  - [x] Create safe markdown diff generation that prevents Telegram API errors from oversized messages
  - [x] Implement diff summary generation for truncated content with line count statistics
  - [x] Limit forensic snapshots to last 3 changes per URL for storage efficiency
  - [x] Write unit tests for snapshot creation, compression, replay, and Telegram safety limits
  - _Requirements: 7.1, 7.2, 4.4_

- [x] 7. Implement circuit breaker pattern for resilient web fetching
  - [x] Create CircuitBreaker class with configurable failure thresholds (3) and recovery timeouts (1h)
  - [x] Implement Finite State Machine (CLOSED, OPEN, HALF_OPEN) for connection health tracking
  - [x] Integrate circuit breaker with GlobalRequestManager to prevent cascading failures
  - [x] Add auto-recovery logic with probing request in HALF_OPEN state
  - [x] Implement immediate fast-fail for requests when circuit is OPEN
  - [x] Write unit tests for state transitions, timeout recovery, and request blocking logic
  - _Requirements: 3.2, 3.4, 5.2_

- [x] 8. Develop anti-bot header rotation and spoofing system
  - [x] Create realistic browser signature pool with User-Agent rotation
  - [x] Implement comprehensive header spoofing (Sec-Ch-Ua, Accept, Accept-Language)
  - [x] Add cookie handling for session-locked websites
  - [x] Create randomized request timing with 1-5 second intervals
  - [x] Implement robots.txt respect and ethical scraping practices
  - [x] Write unit tests for header rotation and timing randomization
  - _Requirements: 3.1, 3.3, 3.5_

- [x] 9. Build structured logging system with correlation IDs
  - [x] Create StructuredLogger class with JSON-formatted output
  - [x] Implement correlation ID tracking using chat_id for cross-component debugging
  - [x] Add comprehensive error context including stack traces and system metrics
  - [x] Create log aggregation for error patterns and system health monitoring
  - [x] Implement log rotation and retention policies
  - [x] Write unit tests for log formatting and correlation ID propagation
  - _Requirements: 5.1, 5.5_

- [x] 10. Implement health monitoring and metrics collection
  - [x] Create system health metrics collection (response times, success rates, worker saturation)
  - [x] Add per-user statistics tracking and reporting
  - [x] Implement health endpoint or admin command for system status
  - [x] Create alerting for critical system metrics and thresholds
  - [x] Add performance monitoring for database operations and web requests
  - [x] Write unit tests for metrics collection and health status reporting
  - _Requirements: 5.1, 6.4_

- [x] 11. Develop enhanced Telegram interface with inline keyboards
  - [x] Create main action menu (Add, List, Settings, Health) triggered by /start
  - [x] Implement smart snooze (1h/6h/24h) and action buttons for alerts
  - [x] Add paginated monitor list with management controls per item
  - [x] Integrate visual diff display into update notifications
  - [x] Create centralized callback query handler for secure button interactions
  - [x] Write unit tests for interface layout and interaction logic
  - _Requirements: 2.1, 2.2, 5.3_, 4.5, 1.4_

- [x] 12. Build user configuration and customization system
  - [x] Create user settings management for similarity thresholds and check intervals
  - [x] Implement global defaults and per-site overrides
  - [x] Create validaton layer to enforce minimum interval (30s)
  - [x] Build interactive settings menu with inline keyboards
  - [x] Write unit tests for configuration persistence and hierarchy resolution
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 13. Implement rate limiting and API compliance
  - [x] Create Global RPS Governor (Tokent Bucket, 5 RPS)
  - [x] Implement Telegram Message Throttler (Strict 30 msg/s queue)
  - [x] Integrate rate limiting into Request Manager (blocking acquire)
  - [x] Implement congestion detection logic (Queue Depth > 50)
  - [x] Write unit tests for timing accuracy and queue draining
  - _Requirements: 8.4, 9.2, 5.2, 5.4_

- [x] 14. Develop change history and data export functionality
  - [x] Implement 30-day change history storage with automatic pruning
  - [x] Create serialized 'HistoryEntry' model
  - [x] Build Data Export Engine (CSV & JSON generators)
  - [x] Update Telegram Interface to view history and trigger exports
  - [x] Write unit tests for retention policy and file generation
  - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] Create data compression strategies for efficient storage usage
  - [x] Update unit tests to verify archival logic
  - _Requirements: 7.1, 7.2, 7.4, 7.5_

- [x] 15. Integrate all components with memory-optimized main controller
  - [x] Refactor main.py into object-oriented WebDogBot class
  - [x] Implement JobBasedDataLoader for efficient monitoring
  - [x] Create centralized startup and shutdown lifecycle management
  - [x] Write integration tests for full system flow
  - [x] Verify memory usage stability under load
  - _Requirements: 8.1, 8.2, 8.3, 8.5_
  - [x] Implement proper dependency injection and component lifecycle management with resource cleanup
  - [x] Add graceful shutdown handling with proper async task cancellation and write queue draining
  - [x] Implement system startup validation and component health checks with failure recovery
  - [x] Create memory usage monitoring and optimization for large-scale deployments
  - [x] Write integration tests for complete monitoring workflows and memory usage patterns
  - _Requirements: 1.1, 1.2, 1.3, 5.3, 6.2_

- [ ] 16. Create comprehensive test suite and validation
  - Develop end-to-end test scenarios covering complete monitoring cycles
  - Create performance tests for concurrent monitoring with 1000+ websites
  - Implement chaos testing for database corruption and network failures
  - Add load testing for Telegram API integration and rate limiting
  - Create test fixtures for algorithm validation with known inputs/outputs
  - Write documentation and deployment guides for production usage
  - _Requirements: 6.1, 6.2, 5.4_