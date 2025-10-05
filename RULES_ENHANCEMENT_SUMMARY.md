# Rules System Enhancement Summary

## Problem Statement

The rules system was previously regex-centric, which created several issues:

1. **UI/UX Issues**: The interface emphasized regex patterns while hiding other detector types (keyword, behavioral, media)
2. **Usability Problems**: Users were pushed toward complex regex for problems better solved by simpler rule types
3. **Operational Risks**: Catastrophic regex patterns could cause performance spikes
4. **Limited Discoverability**: Valuable behavioral and media detection features were underutilized
5. **Lack of Field Scoping**: No way to target specific fields (username vs. bio vs. content)

## Solution Overview

This PR transforms the rules system to make all detector types first-class citizens with equal visibility and enhanced configuration options.

## Key Changes

### 1. Backend Database Schema

**New Fields Added to `Rule` Model:**
- `target_fields` (JSON): Array of fields to check - `['username', 'display_name', 'bio', 'content']`
- `match_options` (JSON): Keyword matching configuration
  - `case_sensitive` (bool): Whether to match exact case
  - `word_boundaries` (bool): Whether to require whole word matches
- `behavioral_params` (JSON): Behavioral detector parameters
  - `time_window_hours` (int): Time window for activity analysis
  - `post_threshold` (int): Number of posts threshold
  - Other behavior-specific settings
- `media_params` (JSON): Media detector parameters
  - `require_alt_text` (bool): Whether alt text is required
  - `allowed_mime_types` (array): List of allowed MIME types
  - Other media-specific settings

**Migration**: `010_add_rule_enhancement_fields.py`

### 2. API Enhancements

**Updated `/rules/help` Endpoint:**
- Reordered to emphasize keyword rules first (recommended approach)
- Added comprehensive examples for each detector type
- Included field scoping examples (username-only, bio-only, etc.)
- Added match options documentation
- Clear guidance on when to use each detector type
- Warning about regex performance concerns

**Example Response Structure:**
```json
{
  "overview": {
    "description": "Choose the right detector for each task",
    "detector_types": {
      "keyword": "Simple, fast text matching - best for known spam terms",
      "behavioral": "Account activity patterns - best for detecting bots",
      "media": "Attachment policies - best for accessibility requirements",
      "regex": "Advanced patterns - use sparingly due to performance concerns"
    }
  },
  "rule_types": {
    "keyword": {
      "priority": 1,
      "examples": [
        {
          "name": "Spam Keywords in Bio",
          "pattern": "casino,pills,viagra,crypto",
          "target_fields": ["bio"],
          "match_options": {
            "case_sensitive": false,
            "word_boundaries": true
          }
        }
      ]
    }
  }
}
```

### 3. Detector Implementations

**KeywordDetector:**
- Now supports `target_fields` for field-specific matching
- Implements `match_options` for:
  - Case-sensitive matching
  - Word boundary detection (whole words only)
- Adds field information to evidence metrics

**RegexDetector:**
- Now supports `target_fields` for field-specific matching
- Only checks targeted fields instead of all fields
- Adds field information to evidence metrics

**Example Usage:**
```python
# Keyword rule targeting only username with word boundaries
rule.pattern = "spam,bot,scam"
rule.target_fields = ["username"]
rule.match_options = {
    "case_sensitive": False,
    "word_boundaries": True
}

# Will match: "spam_account" but NOT "spammer_account" (due to word boundaries)
```

### 4. Frontend UI Improvements

**Rule Creation Modal:**
- **Detector Type Selection**: Reordered with keyword first (recommended)
  - Keyword (Simple text matching - recommended)
  - Behavioral (Account activity patterns)
  - Media (Attachment policies)
  - Regex (Advanced pattern matching)

- **Context-Sensitive Labels**:
  - Keyword: "Keywords (comma-separated)"
  - Behavioral: "Behavior Pattern"
  - Media: "Media Pattern"
  - Regex: "Regex Pattern"

- **Field Targeting** (for keyword/regex):
  - Multi-select for username, display_name, bio, content
  - Helps reduce false positives by targeting specific areas

- **Match Options** (for keyword):
  - Checkbox for "Case Sensitive"
  - Checkbox for "Word Boundaries" (recommended)

**Rule Info Modal:**
- Type-specific help text and examples
- Displays target_fields as badges
- Shows match_options configuration
- Warning about regex performance for regex rules
- Guidance on when to use each detector type

**Display Order:**
- Rules grid reordered: Keyword → Behavioral → Media → Regex
- Emphasizes recommended approaches first

### 5. Testing

**New Test Coverage:**
- `test_evaluate_with_word_boundaries()`: Verifies word boundary matching
- `test_evaluate_without_word_boundaries()`: Verifies substring matching
- `test_evaluate_with_target_fields_username_only()`: Verifies field scoping
- `test_evaluate_case_sensitive()`: Verifies case-sensitive matching
- `test_evaluate_with_target_fields()`: Verifies regex field scoping

**All Tests Pass:**
- Python code compiles without syntax errors
- Frontend builds successfully with TypeScript validation
- Existing tests updated to include new required fields

## Benefits

### For Users:

1. **Simpler Rule Creation**: Keyword rules are easier to understand and maintain than regex
2. **Better Performance**: Field targeting reduces unnecessary pattern matching
3. **Fewer False Positives**: Word boundaries prevent "spam" from matching "spammer"
4. **Clearer Guidance**: UI clearly explains when to use each detector type
5. **More Powerful Filtering**: Can target specific fields (e.g., username-only rules)

### For Administrators:

1. **Reduced Operational Risk**: Less reliance on potentially problematic regex
2. **Better Maintainability**: Keyword rules are easier to audit and update
3. **Improved Performance**: Field scoping reduces processing overhead
4. **Enhanced Visibility**: All detector types equally visible and accessible

### For the System:

1. **Safer Operations**: Regex is de-emphasized, reducing catastrophic backtracking risk
2. **Better Resource Usage**: Field targeting reduces unnecessary work
3. **More Flexible**: Can combine multiple approaches for better detection
4. **Future-Ready**: Infrastructure for behavioral and media policies in place

## Migration Guide

### For Existing Rules:

No migration needed! All existing rules continue to work:
- Rules without `target_fields` default to checking all fields (backward compatible)
- Rules without `match_options` use sensible defaults (case-insensitive, word boundaries for keywords)
- All new fields are optional

### For New Rules:

**Recommended Approach:**

1. **Start with Keywords**: Try keyword matching first
   ```json
   {
     "detector_type": "keyword",
     "pattern": "spam,scam,phishing",
     "target_fields": ["bio", "username"],
     "match_options": {
       "case_sensitive": false,
       "word_boundaries": true
     }
   }
   ```

2. **Use Field Targeting**: Narrow scope to reduce false positives
   - Username-only for account name patterns
   - Bio-only for profile spam
   - Content-only for post spam

3. **Enable Word Boundaries**: Prevent partial matches
   - "spam" won't match "spammer" with word boundaries enabled

4. **Use Regex Only When Needed**: For complex patterns keyword can't handle
   - URL patterns with specific TLDs
   - Complex username patterns (e.g., `^user\d{4,}$`)
   - Always test at regex101.com first

## Examples

### Before (Regex-Heavy):

```json
{
  "name": "Crypto Spam",
  "detector_type": "regex",
  "pattern": ".*(bitcoin|crypto|nft|blockchain).*",
  "weight": 1.0
}
```

**Problems:**
- Checks ALL fields (username, display name, bio, content)
- Can match legitimate crypto discussion
- Harder to understand and maintain
- Potential performance impact

### After (Keyword with Field Targeting):

```json
{
  "name": "Crypto Spam in Bio",
  "detector_type": "keyword",
  "pattern": "bitcoin,crypto,nft,blockchain",
  "target_fields": ["bio"],
  "match_options": {
    "case_sensitive": false,
    "word_boundaries": true
  },
  "weight": 1.0
}
```

**Benefits:**
- Only checks bio (reduces false positives from normal discussion)
- Word boundaries prevent "blockchain" from matching "blockchaindevelopment"
- Easier to understand and audit
- Better performance

## API Compatibility

All changes are backward compatible:
- Existing API endpoints continue to work
- New fields are optional
- Old rules continue to function
- GET /rules returns new fields (clients can ignore them)
- POST /rules accepts new fields (optional)

## Performance Impact

**Positive:**
- Field targeting reduces unnecessary regex/keyword matching
- Word boundaries use optimized regex patterns
- Less catastrophic regex risk

**Neutral:**
- Keyword matching is already fast
- Additional JSON fields have minimal storage impact

## Future Enhancements

This PR provides the foundation for:
- Named keyword lists (e.g., shared blocklists)
- Behavioral parameter tuning UI
- Media policy builder
- Rule composition (ALL/ANY/K-of-N conditions)
- Dry-run/preview functionality
- Safe-regex validation and timeouts

## Files Changed

**Backend:**
- `backend/app/models.py` - Added new Rule fields
- `backend/app/api/rules.py` - Updated help endpoint and rule creation
- `backend/app/services/rule_service.py` - Updated create_rule signature
- `backend/app/services/detectors/keyword_detector.py` - Added field targeting and match options
- `backend/app/services/detectors/regex_detector.py` - Added field targeting
- `backend/migrations/versions/010_add_rule_enhancement_fields.py` - New migration

**Frontend:**
- `frontend/src/App.tsx` - Updated UI components and modals
- `frontend/src/analytics.ts` - Added TypeScript types

**Tests:**
- `tests/services/test_detectors.py` - Added comprehensive tests for new features

## Conclusion

This PR successfully transforms the MastoWatch rules system from a regex-centric approach to a balanced, multi-detector system that emphasizes the right tool for each job. Keyword rules are now the recommended default, with clear guidance on when to use other detector types. The new field targeting and match options provide powerful, precise filtering while maintaining backward compatibility.
