package pk.trustguard.tier1

/**
 * A single Tier-1 rule hit produced by [Tier1Rules.scan].
 *
 * @param label      stable identifier of the matched rule (e.g. "otp_harvesting")
 * @param severity   1..5, higher = more dangerous
 * @param confidence 0.0..1.0 model-free heuristic confidence
 */
data class Tier1Hit(val label: String, val severity: Int, val confidence: Double)

/**
 * Pure-Kotlin, dependency-free on-device scam heuristics ("Tier 1").
 * Runs synchronously in well under a millisecond for typical chat messages,
 * so it is safe to call directly on the UI thread per sent message.
 *
 * Case-insensitive regexes cover English, Roman Urdu and Urdu-script scam
 * phrasing. At most one hit is returned per rule label per scan.
 */
object Tier1Rules {

    private class Rule(val label: String, val severity: Int, val confidence: Double, val regex: Regex)

    private val rules: List<Rule> = listOf(
        Rule(
            "otp_harvesting", 5, 0.6,
            Regex("(?:otp|one[- ]time (?:password|code)|verification code|code batao|کوڈ بتائیں|otp sunao)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "credential_request", 5, 0.65,
            Regex("(?:password|cvv|\\bpin\\b.{0,15}(?:batao|share))", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "bank_impersonation", 4, 0.7,
            Regex("(?:fraud department|ApnaBank.{0,20}(?:fraud|security)|bank security team)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "wallet_impersonation", 4, 0.7,
            Regex("(?:easypaisa|jazz ?cash|raast)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "government_impersonation", 4, 0.7,
            Regex("(?:FBR|NADRA|FIA|cyber ?crime)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "telecom_impersonation", 3, 0.7,
            Regex("(?:sim (?:block|expire)|PTA|Zong|Telenor|Ufone|Jazz team)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "threat_intimidation", 4, 0.7,
            Regex("(?:account block|arrest|legal action|police|جیل|greftar|block ho jayegi|block hone wala)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "urgency_pressure", 3, 0.65,
            Regex("(?:within \\d+ (?:minutes|hours)|turant|foran|abhi hi|right now|today only)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "secrecy_request", 2, 0.7,
            Regex("(?:kisi ko na batana|don'?t tell anyone|confidential|خفیہ|chup?ke rakhna)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "suspicious_link", 4, 0.75,
            Regex("(?:bit\\.ly|tinyurl|click here|t\\.co/)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "upfront_fee_demand", 4, 0.7,
            Regex("(?:registration fee|processing fee|fee jama|advance (?:payment|deposit))", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "prize_lottery_claim", 3, 0.7,
            Regex("(?:you.?ve won|lottery|lucky draw|prize)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "investment_pitch", 2, 0.6,
            Regex("(?:guaranteed (?:returns|profit)|double your (?:money|paisa)|crypto|trading group)", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "account_number_request", 4, 0.7,
            Regex("(?:IBAN|account number.{0,25}(?:bhejo|batao|do|confirm))", RegexOption.IGNORE_CASE)
        ),
        Rule(
            "payment_redirection", 4, 0.7,
            Regex("(?:doosre account|different account|is number par bhejo|personal account)", RegexOption.IGNORE_CASE)
        )
    )

    /**
     * Scans [text] against all Tier-1 rules.
     *
     * @param elapsedTracker optional callback invoked exactly once with the wall-clock
     *                       duration of the regex sweep in whole milliseconds.
     * @return distinct hits — at most one [Tier1Hit] per label per scan.
     */
    fun scan(text: String, elapsedTracker: ((Long) -> Unit)? = null): List<Tier1Hit> {
        val startNs = System.nanoTime()
        val hits = ArrayList<Tier1Hit>(rules.size)
        for (rule in rules) {
            if (rule.regex.containsMatchIn(text)) {
                hits += Tier1Hit(rule.label, rule.severity, rule.confidence)
            }
        }
        elapsedTracker?.invoke((System.nanoTime() - startNs) / 1_000_000L)
        return hits
    }
}
