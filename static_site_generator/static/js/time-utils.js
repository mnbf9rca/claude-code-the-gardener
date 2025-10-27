/**
 * Time expression parsing utilities
 *
 * Parse Grafana-style relative time expressions using modern Date methods
 * Supported formats:
 * - "now" - current time
 * - "now-3h", "now-7d", "now-1M", "now-2y" - relative past
 * - "now+1h", "now+3d" - relative future
 * - "2024-01-15" or "2024-01-15 14:30" - absolute dates
 * - Empty string - interpreted as no filter (all data)
 *
 * Uses Date.prototype methods (setMonth, setDate, etc.) which properly handle:
 * - Leap years
 * - Varying month lengths (28-31 days)
 * - Daylight saving time transitions
 */

/**
 * Parse a time expression and return a Unix timestamp in milliseconds,
 * or null if the expression is invalid or empty.
 *
 * @param {string} expr - The time expression to parse
 * @param {Function} onError - Optional callback for error handling: onError(errorMessage)
 * @returns {number|null} Unix timestamp in milliseconds, or null
 */
function parseTimeExpression(expr, onError) {
    if (!expr || expr.trim() === '') {
        return null; // No filter
    }

    const trimmed = expr.trim();

    // Try parsing as absolute date/datetime
    const absoluteDate = new Date(trimmed);
    if (!isNaN(absoluteDate.getTime()) && trimmed.match(/\d{4}-\d{2}-\d{2}/)) {
        return absoluteDate.getTime();
    }

    // Handle "now" with optional offset
    if (trimmed === 'now') {
        return Date.now();
    }

    // Match: now[+-]<number><unit>
    const relativeMatch = trimmed.match(/^now\s*([+-])\s*(\d+)\s*([smhdwMy])$/);
    if (relativeMatch) {
        const sign = relativeMatch[1] === '+' ? 1 : -1;
        const amount = parseInt(relativeMatch[2]) * sign;
        const unit = relativeMatch[3];

        const date = new Date();

        // Use Date methods for accurate calendar arithmetic
        switch (unit) {
            case 's': // seconds
                date.setSeconds(date.getSeconds() + amount);
                break;
            case 'm': // minutes
                date.setMinutes(date.getMinutes() + amount);
                break;
            case 'h': // hours
                date.setHours(date.getHours() + amount);
                break;
            case 'd': // days
                date.setDate(date.getDate() + amount);
                break;
            case 'w': // weeks
                date.setDate(date.getDate() + (amount * 7));
                break;
            case 'M': // months (handles varying lengths correctly)
                date.setMonth(date.getMonth() + amount);
                break;
            case 'y': // years (handles leap years correctly)
                date.setFullYear(date.getFullYear() + amount);
                break;
        }

        return date.getTime();
    }

    // If we can't parse it, invoke error callback if provided
    const errorMsg = `Unrecognized time filter expression: "${trimmed}"`;
    if (onError && typeof onError === 'function') {
        onError(errorMsg);
    } else {
        console.warn(errorMsg);
    }
    return null;
}
