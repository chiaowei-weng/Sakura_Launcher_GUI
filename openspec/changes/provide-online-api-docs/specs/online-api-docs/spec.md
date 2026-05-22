## ADDED Requirements

### Requirement: Online API documentation endpoint
The system MUST provide a reachable HTTP endpoint at `/docs` that serves a human-readable API documentation page.

#### Scenario: Access documentation via browser
- **WHEN** the user visits `http://<host>:<proxy_port>/docs` in a web browser
- **THEN** the system SHALL return an HTML page containing the API documentation.

### Requirement: Documentation content for OpenAI compatibility
The documentation SHALL clearly list the OpenAI-compatible endpoints supported by the proxy.

#### Scenario: View endpoint details
- **WHEN** the user views the documentation page
- **THEN** they SHALL see the `/v1/chat/completions` endpoint along with its expected JSON payload structure and parameter descriptions.

### Requirement: Traditional Chinese Proxy explanation
The documentation MUST include a section explaining that all responses from this proxy are automatically converted to Taiwan Traditional Chinese.

#### Scenario: Understand conversion behavior
- **WHEN** the user reads the documentation
- **THEN** they SHALL find an explanation of the `zh-tw` conversion logic applied to the LLM outputs.
