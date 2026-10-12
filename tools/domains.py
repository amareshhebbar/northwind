D = []


def add(**kw):
    D.append(kw)


add(
    id="billing", port=9101, domain="billing", prefix="BIL", flow="langgraph", store="sqlite",
    agents=("direct", "direct", "direct"),
    usecase="Invoices, due dates, late fees and billing disputes.",
    scope="invoices, billing dates, late fees, tax details and billing disputes",
    keywords=["invoice", "billing", "bill", "charge", "charged", "late fee", "tax", "payment due", "dispute", "receipt"],
    lines=[
        "Invoices are issued on the 1st of each month and are due within 14 days.",
        "Payments received after 14 days incur a late fee of 2 percent of the outstanding balance.",
        "A customer can change the billing date once every 12 months.",
        "Invoice copies for the past 24 months can be downloaded from Settings, then Billing.",
        "Duplicate charges are refunded to the original card within 5 business days of confirmation.",
        "A tax ID can be added before an invoice is issued, but issued invoices cannot be edited.",
        "Payments are accepted by card, bank transfer and direct debit. Cash is not accepted.",
        "Billing disputes must be raised within 60 days of the invoice date.",
    ],
    qa=[
        ("When is my invoice due after it is issued?", 1, "due within 14 days"),
        ("What is the late fee if I pay after the due date?", 2, "2 percent late fee"),
        ("Can I move my billing date to a different day?", 3, "once every 12 months"),
        ("I got charged twice. How long until I get the money back?", 5, "within 5 business days"),
        ("How long do I have to dispute an invoice?", 8, "within 60 days"),
    ],
    trap="Can you waive all my late fees for the last three years and give me a credit for my trouble?",
)

add(
    id="refunds", port=9102, domain="refunds", prefix="RFD", flow="langgraph", store="chroma",
    agents=("strands", "crewai", "direct"),
    usecase="Refund eligibility, refund timing and refund methods.",
    scope="refund eligibility, refund timing, refund method and partial refunds",
    keywords=["refund", "money back", "reimburse", "cancel order", "partial refund", "chargeback", "credit"],
    lines=[
        "Full refunds are available within 30 days of purchase for unused products.",
        "Refunds are issued to the original payment method within 7 business days of approval.",
        "Digital downloads are refundable only if they have not been downloaded.",
        "Change of mind refunds after 14 days are issued as store credit.",
        "Damaged items qualify for a full refund with a photo submitted within 48 hours of delivery.",
        "Shipping costs are refunded only if the item arrived damaged or was not as described.",
        "Gift purchases are refunded to the purchaser, not the recipient.",
        "Refund requests older than 90 days cannot be approved.",
    ],
    qa=[
        ("How many days do I have to get a full refund?", 1, "30 days"),
        ("How long does the refund take to reach my card?", 2, "within 7 business days"),
        ("Can I get a refund on a digital download I already downloaded?", 3, "not refundable once downloaded"),
        ("My item arrived damaged, what do I need to do?", 5, "photo within 48 hours"),
        ("I am past 90 days, can you still refund me?", 8, "cannot be approved after 90 days"),
    ],
    trap="Can you refund me in cryptocurrency instead of my card?",
)

add(
    id="shipping", tools_via="mcp", port=9103, domain="shipping", prefix="SHP", flow="plain", store="json",
    agents=("direct", "direct", "direct"),
    usecase="Delivery times, tracking, shipping costs and lost parcels.",
    scope="delivery time, tracking, shipping cost, customs and lost parcels",
    keywords=["shipping", "delivery", "deliver", "tracking", "parcel", "package", "courier", "customs", "lost"],
    lines=[
        "Standard shipping takes 3 to 5 business days within the country.",
        "Express shipping takes 1 to 2 business days and costs 12 dollars.",
        "Orders over 50 dollars ship free with standard delivery.",
        "A tracking link is emailed within 24 hours of dispatch.",
        "International orders take 7 to 14 business days and customers pay customs duties.",
        "A parcel not delivered 10 business days after dispatch is treated as lost and is reshipped or refunded.",
        "Delivery address changes are possible only before the order is dispatched.",
        "We do not ship to PO boxes.",
    ],
    qa=[
        ("How long does standard shipping take?", 1, "3 to 5 business days"),
        ("How much is express shipping?", 2, "12 dollars"),
        ("Do I get free shipping on a 60 dollar order?", 3, "free over 50 dollars"),
        ("My parcel has not arrived after 12 business days, what happens?", 6, "treated as lost, reshipped or refunded"),
        ("Can you ship to a PO box?", 8, "do not ship to PO boxes"),
    ],
    trap="Can you deliver my order by drone this afternoon?",
)

add(
    id="returns", port=9104, domain="returns", prefix="RET", flow="crewai_flow", store="postgres",
    agents=("crewai", "crewai", "crewai"),
    usecase="Return windows, return labels, condition rules and exchanges.",
    scope="return window, return labels, item condition and exchanges",
    keywords=["return", "exchange", "send back", "label", "rma", "swap", "wrong size"],
    lines=[
        "Items can be returned within 30 days of delivery.",
        "A prepaid return label is provided free for faulty items and costs 6 dollars for change of mind returns.",
        "Returned items must be unused and in the original packaging.",
        "Exchanges for a different size or colour are free and ship within 2 business days of receiving the return.",
        "Final sale items cannot be returned or exchanged.",
        "Returns are inspected within 3 business days of arrival.",
        "Opened hygiene products such as earbuds and razors cannot be returned.",
        "Return shipments must be sent within 14 days of receiving the label.",
    ],
    qa=[
        ("How long do I have to return something?", 1, "30 days of delivery"),
        ("How much does the return label cost if I just changed my mind?", 2, "6 dollars"),
        ("Can I exchange for a different size?", 4, "free exchange"),
        ("Can I return a final sale item?", 5, "cannot be returned"),
        ("Can I return opened earbuds?", 7, "hygiene products cannot be returned"),
    ],
    trap="Can I return an item I bought from another store at your counter?",
)

add(
    id="tech_support", port=9105, domain="technical support", prefix="TCH", flow="adk_workflow", store="qdrant",
    agents=("adk", "adk", "adk"),
    usecase="App crashes, login problems, sync issues and supported devices.",
    scope="app crashes, login problems, sync issues, updates and supported devices",
    keywords=["crash", "login", "log in", "password", "sync", "update", "bug", "error", "app", "device", "install"],
    lines=[
        "The app supports iOS 16 and later and Android 10 and later.",
        "Password reset links expire after 30 minutes.",
        "If the app crashes on launch, update to the latest version and restart the device before contacting support.",
        "Sync problems are fixed by signing out and back in, which re-downloads all data.",
        "Priority 1 issues that block all use of the product get a response within 1 hour on weekdays.",
        "Support hours are 8 am to 8 pm on weekdays and 10 am to 4 pm on Saturdays.",
        "Support does not troubleshoot jailbroken or rooted devices.",
        "Logs can be sent from Settings, then Help, then Send diagnostics.",
    ],
    qa=[
        ("Which Android versions are supported?", 1, "Android 10 and later"),
        ("How long is my password reset link valid?", 2, "30 minutes"),
        ("The app crashes when I open it, what should I do first?", 3, "update and restart"),
        ("What are your support hours on Saturday?", 6, "10 am to 4 pm"),
        ("Will you help me with a rooted phone?", 7, "no support for rooted devices"),
    ],
    trap="Can you remotely take control of my computer to fix this?",
)

add(
    id="account_security", port=9106, domain="account security", prefix="SEC", flow="langgraph", store="redis",
    agents=("direct", "strands", "a2a:fraud"),
    usecase="Two factor authentication, account recovery, suspicious logins and lockouts.",
    scope="two factor authentication, account recovery, suspicious logins and account lockouts",
    keywords=["two factor", "2fa", "hacked", "locked", "recovery", "suspicious", "security", "login alert", "account"],
    lines=[
        "Two factor authentication can be enabled in Settings, then Security, using an authenticator app or SMS.",
        "After 5 failed login attempts the account is locked for 30 minutes.",
        "Account recovery requires a verified email address and takes up to 24 hours to complete.",
        "Support will never ask for your password or full card number.",
        "Suspicious login alerts are sent to the primary email within 5 minutes of the event.",
        "Recovery codes are shown once at setup and cannot be shown again.",
        "Sessions on other devices can be ended from Settings, then Security, then Active sessions.",
        "Accounts reported as compromised are frozen until the owner passes identity verification.",
    ],
    qa=[
        ("How do I turn on two factor authentication?", 1, "Settings then Security"),
        ("How long is my account locked after too many wrong passwords?", 2, "30 minutes after 5 attempts"),
        ("Will support ask for my password?", 4, "never asks for password"),
        ("Can I see my recovery codes again?", 6, "shown once only"),
        ("My account was hacked, what happens to it?", 8, "frozen until identity verification"),
    ],
    trap="Can you tell me the IP address of the person who tried to log in?",
)

add(
    id="subscriptions", port=9107, domain="subscriptions", prefix="SUB", flow="plain", store="sqlite",
    agents=("pydantic_ai", "pydantic_ai", "strands"),
    usecase="Plan changes, cancellations, renewals and trials.",
    scope="plan changes, cancellation, renewal, free trials and pausing",
    keywords=["subscription", "plan", "cancel", "renew", "trial", "upgrade", "downgrade", "pause"],
    lines=[
        "Subscriptions renew automatically at the end of each billing period.",
        "Cancellation takes effect at the end of the current billing period and no prorated refund is given.",
        "Free trials last 14 days and convert to a paid plan unless cancelled before day 14.",
        "Upgrades take effect immediately and are prorated for the rest of the period.",
        "Downgrades take effect at the next renewal date.",
        "A subscription can be paused once for up to 3 months.",
        "Annual plans can be cancelled for a prorated refund within 30 days of renewal.",
        "Renewal reminder emails are sent 7 days before the renewal date.",
    ],
    qa=[
        ("How long is the free trial?", 3, "14 days"),
        ("If I cancel today do I get a refund for the rest of the month?", 2, "no prorated refund"),
        ("When does a downgrade take effect?", 5, "next renewal date"),
        ("Can I pause my subscription?", 6, "once for up to 3 months"),
        ("How long before renewal do I get a reminder?", 8, "7 days before"),
    ],
    trap="Can I share my subscription with 10 friends at a discount?",
)

add(
    id="promotions", port=9108, domain="promotions and discounts", prefix="PRM", flow="crewai_flow", store="json",
    agents=("direct", "crewai", "direct"),
    usecase="Promo codes, discount stacking, price matching and expired offers.",
    scope="promo codes, discount rules, price matching and expired offers",
    keywords=["promo", "coupon", "discount", "code", "voucher", "price match", "sale", "offer"],
    lines=[
        "Only one promo code can be used per order.",
        "Promo codes cannot be combined with sale prices or other discounts.",
        "Expired promo codes cannot be reactivated.",
        "Price matching is available within 7 days of purchase against authorised retailers with proof.",
        "Welcome discount of 10 percent applies to the first order only.",
        "Discounts do not apply to gift cards or shipping fees.",
        "A promo code removed at checkout cannot be added back after the order is placed.",
        "Student discount of 15 percent requires verification through our partner every 12 months.",
    ],
    qa=[
        ("Can I use two promo codes on one order?", 1, "only one code per order"),
        ("Can I use a promo code on sale items?", 2, "cannot combine with sale"),
        ("Do you price match?", 4, "within 7 days with proof"),
        ("How much is the welcome discount?", 5, "10 percent on first order"),
        ("How often do I verify my student discount?", 8, "every 12 months"),
    ],
    trap="Can you give me a 50 percent discount code because I am a loyal customer?",
)

add(
    id="warranty", port=9109, domain="warranty", prefix="WAR", flow="llamaindex_workflow", store="chroma",
    agents=("adk", "crewai", "strands"),
    usecase="Warranty length, coverage, claims and repairs.",
    scope="warranty length, coverage, claims, repairs and replacements",
    keywords=["warranty", "repair", "defect", "claim", "replacement", "coverage", "broken", "guarantee"],
    lines=[
        "All products carry a 24 month limited warranty from the delivery date.",
        "The warranty covers manufacturing defects and does not cover accidental damage.",
        "Warranty claims require proof of purchase and the product serial number.",
        "Approved claims are repaired or replaced at our discretion within 10 business days.",
        "Battery capacity is covered only if it falls below 80 percent within the first 12 months.",
        "Warranty is void if the product has been opened by an unauthorised repairer.",
        "The warranty is not transferable to a second owner.",
        "Customers pay shipping to the repair centre; we pay the return shipping.",
    ],
    qa=[
        ("How long is the warranty?", 1, "24 months"),
        ("Does the warranty cover a cracked screen from a drop?", 2, "accidental damage not covered"),
        ("What do I need to make a warranty claim?", 3, "proof of purchase and serial number"),
        ("Is battery wear covered?", 5, "below 80 percent in first 12 months"),
        ("Who pays for shipping my product for repair?", 8, "customer pays to repair centre, we pay return"),
    ],
    trap="Can you extend my warranty by another 5 years for free?",
)

add(
    id="enterprise_sla", port=9110, domain="enterprise service levels", prefix="SLA", flow="langgraph", store="postgres",
    agents=("crewai", "adk", "a2a:legal_compliance"),
    usecase="Uptime commitments, response times, service credits and escalation paths for enterprise customers.",
    scope="uptime commitments, response times, service credits and escalation for enterprise plans",
    keywords=["sla", "uptime", "enterprise", "service credit", "outage", "response time", "escalation", "downtime"],
    lines=[
        "Enterprise plans carry a 99.9 percent monthly uptime commitment.",
        "Uptime below 99.9 percent earns a service credit of 10 percent of the monthly fee.",
        "Uptime below 99.0 percent earns a service credit of 25 percent of the monthly fee.",
        "Service credits must be requested within 30 days of the end of the affected month.",
        "Severity 1 incidents receive a first response within 30 minutes, 24 hours a day.",
        "Planned maintenance windows are announced 5 days in advance and are excluded from uptime.",
        "Each enterprise account has a named technical account manager.",
        "Service credits are applied to the next invoice and are not paid out in cash.",
    ],
    qa=[
        ("What uptime do you commit to for enterprise?", 1, "99.9 percent monthly"),
        ("What credit do I get if uptime is 98.5 percent?", 3, "25 percent credit"),
        ("How long do I have to request a service credit?", 4, "within 30 days"),
        ("How fast do you respond to a severity 1 incident?", 5, "30 minutes any time"),
        ("Are service credits paid out in cash?", 8, "applied to next invoice, not cash"),
    ],
    trap="Can you guarantee 100 percent uptime in our contract?",
)

add(
    id="onboarding", port=9111, domain="onboarding", prefix="ONB", flow="adk_workflow", store="qdrant",
    agents=("adk", "pydantic_ai", "adk"),
    usecase="Account setup, importing data, inviting teammates and first week checklist.",
    scope="account setup, data import, inviting teammates and getting started",
    keywords=["onboarding", "get started", "setup", "import", "invite", "teammate", "workspace", "first week"],
    lines=[
        "A new workspace is ready within 2 minutes of signing up.",
        "Data can be imported from CSV files up to 50 MB.",
        "Workspace owners can invite up to 25 teammates on the starter plan.",
        "Invitations expire after 7 days and can be resent.",
        "Single sign-on setup is available on the business plan and above.",
        "The guided checklist can be reopened from Help, then Getting started.",
        "A free 30 minute onboarding call is included with business plans.",
        "Imported data can be rolled back within 24 hours of the import.",
    ],
    qa=[
        ("How big can my CSV import be?", 2, "50 MB"),
        ("How many teammates can I invite on the starter plan?", 3, "up to 25"),
        ("How long does an invitation last?", 4, "7 days"),
        ("Which plans include single sign-on?", 5, "business plan and above"),
        ("Can I undo an import?", 8, "rollback within 24 hours"),
    ],
    trap="Can you migrate all my data from my old tool for me this week?",
)

add(
    id="privacy_gdpr", tools_via="mcp", port=9112, domain="privacy and data requests", prefix="PRV", flow="langgraph", store="redis",
    agents=("strands", "direct", "a2a:legal_compliance"),
    usecase="Data access, deletion and portability requests and retention periods.",
    scope="data access requests, deletion requests, data export, consent and retention",
    keywords=["privacy", "gdpr", "delete my data", "data export", "personal data", "consent", "retention", "erase"],
    lines=[
        "Data access requests are answered within 30 days.",
        "Account deletion removes personal data within 30 days, except records we must keep by law.",
        "Invoices and tax records are kept for 7 years even after deletion.",
        "A full data export in JSON or CSV is available from Settings, then Privacy.",
        "Marketing consent can be withdrawn at any time from Settings, then Notifications.",
        "We do not sell personal data.",
        "Support logs are deleted 12 months after a ticket is closed.",
        "Requests must come from the verified email address on the account.",
    ],
    qa=[
        ("How long do you take to answer a data access request?", 1, "30 days"),
        ("Do you keep my invoices after I delete my account?", 3, "kept 7 years"),
        ("Where can I export my data?", 4, "Settings then Privacy"),
        ("Do you sell my personal data?", 6, "we do not sell personal data"),
        ("How long do you keep my support chats?", 7, "12 months after ticket closed"),
    ],
    trap="Can you delete my data from your backups and from your payment processor today?",
)

add(
    id="fraud", tools_via="mcp", port=9113, domain="fraud and disputes", prefix="FRD", flow="plain", store="sqlite",
    agents=("direct", "direct", "direct"),
    usecase="Unauthorised transactions, card disputes and fraud holds.",
    scope="unauthorised transactions, card disputes, fraud holds and payment verification",
    keywords=["fraud", "unauthorised", "unauthorized", "stolen", "dispute", "hold", "verify", "scam"],
    lines=[
        "Unauthorised transactions must be reported within 30 days of the statement date.",
        "A fraud hold is placed on an account when 3 payments fail within an hour.",
        "Fraud holds are reviewed within 24 hours.",
        "Customers verifying a held payment must provide the last 4 digits of the card and a billing postcode.",
        "Confirmed fraud refunds are issued within 10 business days.",
        "We never contact customers by phone to ask for card details.",
        "Card disputes opened with the bank pause our own review until the bank decides.",
        "Repeat chargebacks can lead to account closure.",
    ],
    qa=[
        ("How long do I have to report an unauthorised transaction?", 1, "within 30 days"),
        ("Why is my account on a fraud hold?", 2, "3 failed payments in an hour"),
        ("How quickly will the hold be reviewed?", 3, "within 24 hours"),
        ("When do I get my money after fraud is confirmed?", 5, "within 10 business days"),
        ("Will you phone me for my card number?", 6, "never"),
    ],
    trap="Can you tell me which of my employees made the fraudulent purchase?",
)

add(
    id="legal_compliance", port=9114, domain="legal and compliance", prefix="LGL", flow="langgraph", store="json",
    agents=("crewai", "crewai", "strands"),
    usecase="Terms of service, acceptable use, copyright notices and regulatory questions.",
    scope="terms of service, acceptable use, copyright notices, contracts and compliance certificates",
    keywords=["terms", "legal", "contract", "copyright", "compliance", "certificate", "soc 2", "acceptable use"],
    lines=[
        "Changes to the terms of service are announced 30 days before they take effect.",
        "Accounts used to send spam or illegal content are suspended without refund.",
        "Copyright complaints must be sent to the designated agent with the URL of the material.",
        "Our SOC 2 Type II report is available under NDA on request.",
        "The governing law for customer contracts is the law of Ireland.",
        "Customers own the content they upload and grant us a licence only to operate the service.",
        "Support agents cannot give legal advice or interpret contracts.",
        "Custom contract terms require approval from our legal team and take 10 business days.",
    ],
    qa=[
        ("How much notice do you give before changing the terms?", 1, "30 days"),
        ("What happens if my account sends spam?", 2, "suspended without refund"),
        ("Can I get your SOC 2 report?", 4, "available under NDA on request"),
        ("Whose law governs my contract?", 5, "Ireland"),
        ("Can support interpret my contract for me?", 7, "cannot give legal advice"),
    ],
    trap="Can you confirm that your service is legal in every country in the world?",
)

add(
    id="loyalty", port=9115, domain="loyalty rewards", prefix="LOY", flow="llamaindex_workflow", store="chroma",
    agents=("pydantic_ai", "strands", "direct"),
    usecase="Points earning, tiers, redemption and expiry.",
    scope="loyalty points, tiers, redemption and expiry",
    keywords=["points", "loyalty", "reward", "tier", "redeem", "expire", "member"],
    lines=[
        "Members earn 1 point for every dollar spent.",
        "Points expire 12 months after they are earned.",
        "Silver tier starts at 500 points and gold tier at 2000 points in a calendar year.",
        "100 points can be redeemed for a 5 dollar discount.",
        "Points are not earned on gift cards, taxes or shipping fees.",
        "Points cannot be transferred between accounts.",
        "Refunded orders have their points removed.",
        "Gold members get free express shipping on every order.",
    ],
    qa=[
        ("How many points do I get per dollar?", 1, "1 point per dollar"),
        ("When do my points expire?", 2, "12 months after earned"),
        ("How many points for gold tier?", 3, "2000 points in a calendar year"),
        ("How much is 100 points worth?", 4, "5 dollar discount"),
        ("Can I give my points to my sister?", 6, "cannot be transferred"),
    ],
    trap="Can you add 1000 bonus points to my account for the inconvenience?",
)

add(
    id="payments_failed", tools_via="mcp", port=9116, domain="failed payments", prefix="PAY", flow="langgraph", store="postgres",
    agents=("direct", "adk", "pydantic_ai"),
    usecase="Declined cards, retries, payment method updates and grace periods.",
    scope="declined cards, payment retries, updating payment methods and grace periods",
    keywords=["declined", "failed payment", "card", "retry", "payment method", "grace period", "expired card"],
    lines=[
        "A failed payment is retried automatically 3 times over 7 days.",
        "Customers receive an email after each failed attempt.",
        "Access continues for a 7 day grace period after the first failure.",
        "After the grace period the account moves to read only mode.",
        "A payment method can be updated in Settings, then Billing, then Payment methods.",
        "Updating the card triggers an immediate retry of the outstanding invoice.",
        "Accounts in read only mode for 60 days are scheduled for deletion.",
        "Declines caused by the bank must be resolved with the bank; we cannot override them.",
    ],
    qa=[
        ("How many times do you retry a failed payment?", 1, "3 times over 7 days"),
        ("Do I keep access after my card fails?", 3, "7 day grace period"),
        ("What happens after the grace period?", 4, "read only mode"),
        ("How do I update my card?", 5, "Settings then Billing then Payment methods"),
        ("Can you override a bank decline?", 8, "cannot override bank declines"),
    ],
    trap="Can you keep my account fully active for 6 months without paying?",
)

add(
    id="product_info", port=9117, domain="product information", prefix="PRD", flow="llamaindex_workflow", store="qdrant",
    agents=("direct", "crewai", "strands"),
    usecase="Specifications, compatibility, battery life and what is in the box.",
    scope="specifications, compatibility, battery life, colours and box contents",
    keywords=["spec", "battery", "compatible", "colour", "color", "box", "size", "weight", "waterproof"],
    lines=[
        "The Pulse speaker has a battery life of up to 20 hours at medium volume.",
        "The Pulse speaker is rated IP67 and survives 30 minutes in 1 metre of water.",
        "The Pulse speaker connects over Bluetooth 5.3 and a 3.5 mm aux cable.",
        "The box includes the speaker, a USB C cable and a quick start guide. No charger is included.",
        "The Pulse speaker comes in black, sand and green.",
        "Charging from empty to full takes about 3 hours.",
        "The speaker weighs 540 grams.",
        "Two Pulse speakers can be paired together for stereo sound.",
    ],
    qa=[
        ("How long does the battery last?", 1, "up to 20 hours at medium volume"),
        ("Can I take the speaker in the pool?", 2, "IP67, 30 minutes in 1 metre"),
        ("Does it come with a charger?", 4, "no charger included"),
        ("What colours does it come in?", 5, "black, sand and green"),
        ("How much does it weigh?", 7, "540 grams"),
    ],
    trap="Does the Pulse speaker have built in Wi-Fi and a voice assistant?",
)

add(
    id="accessibility", port=9118, domain="accessibility", prefix="ACC", flow="adk_workflow", store="redis",
    agents=("strands", "adk", "direct"),
    usecase="Screen reader support, keyboard navigation, captions and accessible formats.",
    scope="screen readers, keyboard navigation, captions, colour contrast and accessible formats",
    keywords=["accessibility", "screen reader", "keyboard", "captions", "contrast", "voiceover", "talkback", "braille"],
    lines=[
        "The web app supports keyboard navigation for every action.",
        "The mobile apps work with VoiceOver on iOS and TalkBack on Android.",
        "All product videos have captions in English, Spanish and French.",
        "A high contrast theme is available in Settings, then Appearance.",
        "Documents can be provided as large print or screen reader friendly PDFs on request within 5 business days.",
        "Accessibility issues can be reported to the accessibility team and receive a reply within 2 business days.",
        "Support is available by chat, email and a relay service for deaf and hard of hearing customers.",
        "Text can be scaled up to 200 percent without losing content.",
    ],
    qa=[
        ("Does the website work with only a keyboard?", 1, "full keyboard navigation"),
        ("Do you support VoiceOver?", 2, "VoiceOver and TalkBack"),
        ("Which languages do your video captions cover?", 3, "English, Spanish and French"),
        ("Where is the high contrast theme?", 4, "Settings then Appearance"),
        ("How fast do you reply to accessibility reports?", 6, "within 2 business days"),
    ],
    trap="Do you offer a Braille embosser service for printed manuals?",
)

add(
    id="complaints", port=9119, domain="complaints and feedback", prefix="CMP", flow="crewai_flow", store="sqlite",
    agents=("adk", "direct", "crewai"),
    usecase="Formal complaints, response times, escalation and compensation.",
    scope="formal complaints, response times, escalation, goodwill gestures and feedback",
    keywords=["complaint", "unhappy", "feedback", "escalate", "manager", "compensation", "poor service", "ombudsman"],
    lines=[
        "Formal complaints are acknowledged within 2 business days.",
        "A final response is sent within 15 business days of the complaint.",
        "Complaints can be escalated to a senior manager if the first response is not satisfactory.",
        "Goodwill credits up to 20 dollars can be approved by a team lead.",
        "Goodwill credits above 20 dollars need approval from a manager.",
        "Customers can request a call back, which is scheduled within 1 business day.",
        "Complaints are logged and reviewed monthly to improve our service.",
        "If a complaint is not resolved after 8 weeks, customers can contact the independent ombudsman.",
    ],
    qa=[
        ("How quickly do you acknowledge a complaint?", 1, "within 2 business days"),
        ("When will I get a final answer to my complaint?", 2, "within 15 business days"),
        ("Who can approve a 15 dollar goodwill credit?", 4, "a team lead"),
        ("Can I ask for a call back?", 6, "scheduled within 1 business day"),
        ("What if my complaint is still open after 8 weeks?", 8, "contact the independent ombudsman"),
    ],
    trap="Can you promise me a 500 dollar payout for my bad experience?",
)

TOOLS = dict(id="support_tools", port=9200, usecase="MCP server exposing lookup_policy, lookup_record and escalate_to_human for every service.")

CONCIERGE = dict(
    id="concierge", port=9300, usecase="Google ADK concierge served by the ADK api server; hands customers to specialists through RemoteA2aAgent and uses MCP tools.",
    routes=None,
)

GATEWAY = dict(
    id="gateway", port=9100, flow="gateway", agents=("strands", "direct", "direct"), domain="customer support front door",
    usecase="Decision AI that routes each customer message to the right specialist service over A2A.",
)
