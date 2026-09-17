"""Content model for the MOSAIC Learn prototype v3.

Drivers content stays close to the supplied MOSAIC Learn attachment.
The Policy Lab / Community module is grounded in the existing MOSAIC Learn Coda
pages (Policy Labs for Land-Use Change and its six building blocks). The content
is intentionally condensed for the prototype rather than migrated verbatim.
"""

LEVEL_META = {
    "Understand": {
        "number": "01",
        "verb": "Understand",
        "tagline": "Build the shared language and concepts.",
        "icon": "◌",
    },
    "Apply": {
        "number": "02",
        "verb": "Apply",
        "tagline": "Use the ideas in policy, research or practice.",
        "icon": "↗",
    },
    "Convince": {
        "number": "03",
        "verb": "Convince",
        "tagline": "Use evidence, examples and resources to bring others with you.",
        "icon": "✦",
    },
}


def card(title, text, label="Core idea", bullets=None):
    return {"title": title, "text": text, "label": label, "bullets": bullets or []}


MODULES = {
    "policy-lab": {
        "title": "Policy Labs for Land-Use Change",
        "short_title": "Policy Lab Foundations",
        "track": "Community",
        "track_icon": "◫",
        "description": (
            "A practical learning journey for setting up a Policy Lab around a shared land-use challenge, "
            "from finding the right focus to building a team, engaging stakeholders and planning for action."
        ),
        "estimated_minutes": 75,
        "status": "Available",
        "eyebrow": "Structured collaboration",
        "source_note": "Condensed from the MOSAIC Learn Policy Lab module and D2.1-based building blocks.",
        "learning_outcomes": [
            "Clarify a shared policy challenge and recognise a useful window of opportunity.",
            "Build a small Core Group that connects policy, research and practice.",
            "Map the policy and institutional landscape before jumping to solutions.",
            "Identify and prioritise stakeholders, including missing or sceptical voices.",
            "Sequence stakeholder, research and policy activities into a coherent workplan.",
            "Create a clear main message that explains purpose, timing and expected roles.",
        ],
        "building_blocks": [
            ("Focus", "What is the challenge — and why now?"),
            ("Core Group", "Who can actually move this forward?"),
            ("Policy Mapping", "Where are decisions made and influenced?"),
            ("Stakeholders", "Who is affected, influential or missing?"),
            ("Workplan", "How should interactions build on each other?"),
            ("Main Message", "What should people understand and do?"),
        ],
        "entry_points": [
            ("focus", "Focus — What is the policy challenge, and why now?"),
            ("core-group", "Core Group — Who are the people who can really move this?"),
            ("policy-mapping", "Policy Mapping — Which policies and institutions shape the issue?"),
            ("stakeholders", "Stakeholders — Who is affected, influential, missing or sceptical?"),
            ("workplan", "Workplan — What must happen before the next real decision moment?"),
            ("main-message", "Main Message — What would you ask the right person to do in 30 seconds?"),
        ],
        "topics": [
            {
                "id": "policy-lab-intro",
                "title": "What a Policy Lab is — and is not",
                "level": "Understand",
                "minutes": 10,
                "summary": "Start with the purpose: structured collaboration around a real policy challenge.",
                "body": (
                    "Policy innovation requires more than expertise. A Policy Lab creates a structured process in which "
                    "researchers, policymakers and stakeholders work together on a shared policy challenge."
                ),
                "theory_cards": [
                    card(
                        "Evidence alone does not create change",
                        "Land-use governance involves competing priorities, institutions and interests. Scientific knowledge may arrive too late, policy may be developed under uncertainty, and stakeholders may be involved without a clear role.",
                        "The challenge",
                    ),
                    card(
                        "A Policy Lab organises collaboration where decisions are shaped",
                        "The Policy Lab is a sustained, interdisciplinary process that connects knowledge, decision-making and practice around a shared challenge.",
                        "The response",
                    ),
                    card(
                        "It is more than participation",
                        "A Policy Lab is not a one-off participatory event, a consultation exercise or a dissemination activity. The collaboration continues and builds toward actionable policy outputs.",
                        "Important distinction",
                    ),
                    card(
                        "Timing matters",
                        "Policy innovation becomes possible when attention, timing and viable solutions align. Policy Labs can help recognise these windows of opportunity and coordinate action before they close.",
                        "Window of opportunity",
                    ),
                ],
                "takeaway": "Think of a Policy Lab as a sustained bridge between evidence, policy processes and stakeholder practice — not as another workshop.",
                "prompt": "Where in your current work do evidence, decision-making and stakeholder experience fail to connect?",
                "practice_note": "The MOSAIC module frames Policy Labs as a response to competing land-use claims, institutional fragmentation and the science–policy gap.",
                "self_check": [
                    "Is there a shared policy challenge rather than only a research topic?",
                    "Is there a real decision process or opportunity to connect to?",
                    "Will stakeholders have a meaningful role beyond being consulted once?",
                ],
                "quiz": {
                    "question": "Which description best fits a Policy Lab in the MOSAIC module?",
                    "options": [
                        "A one-off workshop used to collect stakeholder opinions.",
                        "A sustained collaborative process around a shared policy challenge.",
                        "A communication campaign for completed research results.",
                    ],
                    "answer": 1,
                    "explanation": "The module describes the Policy Lab as a sustained collaborative process, not a one-off event or dissemination exercise.",
                },
            },
            {
                "id": "focus",
                "title": "Find the right focus",
                "level": "Apply",
                "minutes": 10,
                "summary": "Bring societal concern, policy opportunity and knowledge need into one shared focus.",
                "body": "A strong focus gives the Policy Lab legitimacy, relevance and a reason to act now.",
                "theory_cards": [
                    card(
                        "A focus is more than a topic",
                        "A Policy Lab is strongest when researchers, policymakers and societal actors agree on a challenge that matters now. Complete agreement is not required, but there must be enough shared purpose to collaborate.",
                        "Shared purpose",
                    ),
                    card(
                        "Look for the overlap",
                        "The MOSAIC focus tool connects three elements: a pressing societal concern, a real policy opportunity and a genuine need for knowledge.",
                        "Three-part focus",
                        ["Societal concern", "Policy opportunity", "Knowledge need"],
                    ),
                    card(
                        "The 'why now?' question is strategic",
                        "Upcoming decisions, revisions, funding programmes or implementation challenges can create a window in which evidence and collaboration have a direct route into policy.",
                        "Timing",
                    ),
                    card(
                        "Co-design creates ownership",
                        "People are more likely to support and use outcomes when they help shape the focus from the beginning rather than being asked to fit into a predetermined agenda.",
                        "Legitimacy",
                    ),
                ],
                "takeaway": "A useful focus sits where policy urgency, research relevance and societal concern overlap.",
                "prompt": "Write your challenge in one sentence, then add: why does this matter now?",
                "practice_note": "In the Swiss Policy Lab, upcoming spatial planning decisions for large-scale solar created a concrete policy window. In Belgium, allowing stakeholders to help shape the topic strengthened ownership.",
                "tool": {"id": "finding-your-focus", "name": "Finding Your Focus", "description": "Use three prompts — societal concern, policy opportunity and knowledge need — to define a shared Core Focus."},
                "self_check": [
                    "Do researchers, policymakers and stakeholders describe the challenge in similar terms?",
                    "Can people explain why the issue matters now?",
                    "Have stakeholders had real influence on the focus?",
                    "Is there a concrete decision process the work could support?",
                ],
                "quiz": None,
            },
            {
                "id": "core-group",
                "title": "Build the Core Group",
                "level": "Apply",
                "minutes": 10,
                "summary": "Create the small steering team that keeps policy, research and practice connected.",
                "body": "The Core Group provides direction, continuity and the bridge between different professional worlds.",
                "theory_cards": [
                    card(
                        "The Core Group is the steering wheel",
                        "A small group needs to provide direction, coordinate activities and make sure knowledge can be translated into real-world action.",
                        "Purpose",
                    ),
                    card(
                        "Expertise is not enough",
                        "A strong Core Group also depends on trust, clear roles, knowledge sharing and continuity. People may need to bridge different professional languages and networks.",
                        "Team quality",
                    ),
                    card(
                        "Make tacit knowledge visible",
                        "When critical knowledge lives only in individual experience or informal conversations, onboarding and continuity become fragile. Capture the history, assumptions and earlier decisions that newcomers need.",
                        "Continuity",
                    ),
                    card(
                        "Discuss personal ambitions",
                        "Researchers, policymakers and facilitators may enter with different goals. Making those ambitions explicit can create a common language and stronger motivation to collaborate.",
                        "Trust",
                    ),
                ],
                "takeaway": "Choose a Core Group for its ability to connect worlds and sustain the process, not only for formal expertise.",
                "prompt": "Who are the two or three people who can move your Policy Lab forward, and what does each need from the collaboration?",
                "practice_note": "MOSAIC Policy Labs encountered tacit knowledge, staff turnover, multiple hats and differences in professional language. Informal conversations about personal ambitions helped build common understanding.",
                "tool": {"id": "define-core-group", "name": "Define Your Core Group", "description": "Clarify strengths, roles, responsibilities, meeting rhythm and the profiles needed for functions such as policy lead and knowledge broker."},
                "self_check": [
                    "Who is best at facilitating and moderating?",
                    "Who connects to policymakers and who connects to local stakeholders?",
                    "Who holds important historical or contextual knowledge?",
                    "Are roles clear enough to survive staff changes?",
                ],
                "quiz": None,
            },
            {
                "id": "policy-mapping",
                "title": "Map the policy landscape",
                "level": "Apply",
                "minutes": 10,
                "summary": "Understand where decisions are made, who influences them and when intervention is possible.",
                "body": "Policy mapping slows the process down at the right moment so action can become more targeted later.",
                "theory_cards": [
                    card(
                        "Do not jump straight to solutions",
                        "Policies interact across sectors, governance levels and stages of the policy cycle. Without understanding that landscape, good ideas can be mistimed or misaligned.",
                        "Why map",
                    ),
                    card(
                        "Map decisions, not only documents",
                        "Identify which policies matter, where decisions are made, who formally decides, who influences them and where the relevant policy process currently sits.",
                        "What to map",
                    ),
                    card(
                        "Timing changes the value of evidence",
                        "The same evidence can be useful or irrelevant depending on when it enters a policy process. Mapping helps identify realistic entry points before final results are produced.",
                        "Policy timing",
                    ),
                    card(
                        "Visuals reveal hidden complexity",
                        "Even a rough map can expose overlaps, conflicting definitions, missing actors and cross-level dependencies that remain invisible when each policy is examined separately.",
                        "Make it visible",
                    ),
                ],
                "takeaway": "Map what matters: policies, actors, relationships, governance levels and decision moments.",
                "prompt": "Which one policy process is most relevant to your challenge, and where is the next realistic point of influence?",
                "practice_note": "The Belgian Policy Lab used mapping to expose fragmentation across grassland policies. The Portuguese Policy Lab used policy-cycle mapping to improve the timing of engagement.",
                "tool": {"id": "policy-mapping", "name": "Policy Mapping", "description": "Build a focused picture of relevant policies, actors, decision points and stages in the policy cycle."},
                "self_check": [
                    "Do you know which policies directly affect your focus?",
                    "Can you locate them in the policy cycle?",
                    "Do you know who influences the formal decision-makers?",
                    "Can you explain where the Policy Lab can realistically make a difference?",
                ],
                "quiz": {
                    "question": "What is the main purpose of policy mapping in this module?",
                    "options": [
                        "To create the largest possible inventory of policy documents.",
                        "To understand where decisions are made, who influences them and when intervention is possible.",
                        "To replace stakeholder engagement with desk research.",
                    ],
                    "answer": 1,
                    "explanation": "The module uses mapping to target action by understanding decision processes, actors and timing.",
                },
            },
            {
                "id": "stakeholders",
                "title": "Involve the right stakeholders",
                "level": "Apply",
                "minutes": 10,
                "summary": "Move from an invitation list to an ongoing strategy for meaningful participation.",
                "body": "The quality of a Policy Lab depends on who is involved, how they contribute and whether different voices can shape decisions.",
                "theory_cards": [
                    card(
                        "Stakeholder involvement is continuous",
                        "It is more than inviting people to a workshop. Keep identifying actors, interests, influence, knowledge and relationships throughout the Policy Lab lifecycle.",
                        "Participation",
                    ),
                    card(
                        "Presence is not the same as influence",
                        "A diverse room can still reproduce power imbalances. Ask whose voices are heard, whose knowledge counts and whether sceptical or less powerful actors can shape the process.",
                        "Power",
                    ),
                    card(
                        "Prioritise deliberately",
                        "Different actors may need to be informed, consulted, involved or empowered in different ways. Influence, interest, legitimacy, urgency, openness and knowledge can help structure those choices.",
                        "Strategy",
                    ),
                    card(
                        "Relationships affect participation",
                        "Existing networks, place attachment, trust and the format of interaction can strongly affect motivation. Online efficiency does not automatically create personal connection or safe participation.",
                        "Engagement quality",
                    ),
                ],
                "takeaway": "Do not only ask who should attend. Ask who shapes outcomes, who is missing, and what meaningful participation looks like for each group.",
                "prompt": "Name one actor you may be overlooking. What would make participation worthwhile and safe for them?",
                "practice_note": "Belgian participants were highly engaged when local actors helped shape the process early and could build on existing networks. The Portuguese Policy Lab found that online participation could limit informal connection and openness.",
                "tool": {"id": "stakeholder-analysis", "name": "Stakeholder Analysis", "description": "Use influence, interest and other dimensions to identify, prioritise and revisit who should be involved and how."},
                "self_check": [
                    "Who really shapes decisions, and who is missing?",
                    "Where do resistance, support or silence come from?",
                    "Are different voices heard or merely present?",
                    "Have you included sceptical actors early enough?",
                ],
                "quiz": None,
            },
            {
                "id": "workplan",
                "title": "Create a coherent workplan",
                "level": "Apply",
                "minutes": 10,
                "summary": "Sequence activities so stakeholder, research and policy interactions build on each other.",
                "body": "A Policy Lab is not a series of disconnected meetings. Its activities need a logical flow and connection to real-world rhythms.",
                "theory_cards": [
                    card(
                        "Plan the journey, not the event calendar",
                        "A coherent workplan connects workshops, research milestones and policy moments so knowledge generated in one interaction can inform the next.",
                        "Sequence",
                    ),
                    card(
                        "Start from real rhythms",
                        "Policy revisions, consultations, deadlines, research milestones and existing stakeholder events create constraints and opportunities. Plan around them rather than creating parallel processes by default.",
                        "Timing",
                    ),
                    card(
                        "Protect stakeholder attention",
                        "Repeated requests without visible progress can cause fatigue. Every interaction should have a clear purpose and show how contributions move the work forward.",
                        "Engagement",
                    ),
                    card(
                        "Balance efficiency and relationships",
                        "Online meetings may be efficient, while field visits, informal conversations and face-to-face moments can build trust and shared understanding. The right mix depends on the context.",
                        "Format",
                    ),
                ],
                "takeaway": "Ask how each interaction contributes to the overall journey — not only what the next event is.",
                "prompt": "What is the next real policy or project date you must meet, and which stakeholder interaction should happen before it?",
                "practice_note": "Some MOSAIC Policy Labs used a 'plug-in' approach, connecting to existing meetings instead of creating new events. Teams also reported stakeholder fatigue when repeated interactions did not show visible progress.",
                "tool": {"id": "timeline-workshop", "name": "Timeline Workshop", "description": "Place policy deadlines and institutional rhythms first, then research milestones and stakeholder interactions, and sense-check the sequence for overload and gaps."},
                "self_check": [
                    "Can you explain the flow from one interaction to the next?",
                    "Are you using existing meetings or policy moments where useful?",
                    "Does each interaction have a clear purpose and output?",
                    "Are stakeholders being overloaded or asked to repeat themselves?",
                ],
                "quiz": None,
            },
            {
                "id": "main-message",
                "title": "Build the main message",
                "level": "Apply",
                "minutes": 15,
                "summary": "Explain what the Policy Lab is about, why it matters now and what role others can play.",
                "body": "A Policy Lab cannot build support when its purpose, ambitions or expected roles are unclear.",
                "theory_cards": [
                    card(
                        "People support what they understand",
                        "A strong message explains the challenge, the Policy Lab's contribution and the role you want others to play. Urgency alone is not enough.",
                        "Clarity",
                    ),
                    card(
                        "Make your own ambition concrete",
                        "Stakeholders need to know what the Policy Lab itself will contribute. Explain the intended activities and outcomes rather than only repeating the seriousness of the problem.",
                        "Contribution",
                    ),
                    card(
                        "One generic message is rarely enough",
                        "Different audiences care about different outcomes, constraints and values. Tailor language, examples and emphasis to the people you want to engage.",
                        "Audience",
                    ),
                    card(
                        "The channel is part of the message strategy",
                        "Existing networks, conferences and intermediaries can sometimes reach the right people more effectively than contacting every organisation individually.",
                        "Reach",
                    ),
                ],
                "takeaway": "A clear main message says what this is, why now, what you will contribute and what you want the audience to do.",
                "prompt": "Write a 30-second message for one specific audience. End with the role or action you want from them.",
                "practice_note": "MOSAIC teams found that messages needed to clarify the contribution of the Policy Lab, adapt to place and audience, and use the right existing channels to reach decision-makers.",
                "tool": {"id": "30-second-message", "name": "30-second message", "description": "Draft one short message around purpose, timing, contribution and a clear ask, then adapt it for a second audience."},
                "self_check": [
                    "How much of your message explains the challenge versus your own ambition?",
                    "Is the expected role of the audience clear?",
                    "Would you use the same message for farmers and policymakers?",
                    "Which existing network or channel could carry the message further?",
                ],
                "quiz": {
                    "question": "What should a strong Policy Lab message make clear?",
                    "options": [
                        "Only why the land-use problem is urgent.",
                        "The purpose, why it matters now, the Policy Lab's contribution and the audience's role.",
                        "As much technical detail as possible so nobody can disagree.",
                    ],
                    "answer": 1,
                    "explanation": "The module stresses clarity about purpose, timing, contribution and the role expected from different stakeholders.",
                },
            },
        ],
    },
    "drivers": {
        "title": "Drivers of Change: Understanding Land-Use as a System",
        "short_title": "Drivers of Change",
        "track": "Learning",
        "track_icon": "◎",
        "description": (
            "A practical guide for understanding why land-use decisions happen and "
            "where policy, research, or field action can make a difference."
        ),
        "estimated_minutes": 35,
        "status": "Available",
        "eyebrow": "Land-use systems",
        "source_note": "Condensed from the supplied Drivers of Change MOSAIC Learn page.",
        "learning_outcomes": [
            "Recognise land-use change as the result of interacting drivers rather than one cause.",
            "Ask which drivers matter for which actor, in which place, and under which conditions.",
            "Spot where implementation gaps can emerge between high-level goals and local decisions.",
            "Communicate a more convincing, actor-aware explanation of proposed change.",
        ],
        "driver_groups": [
            ("Economic pressures", "Prices, costs and livelihoods"),
            ("Technology & climate", "Tools, infrastructure and conditions"),
            ("Policy signals", "Rules, incentives and regulation"),
            ("People, values & trust", "Identity, relationships and beliefs"),
        ],
        "topics": [
            {
                "id": "drivers-as-system",
                "title": "Land-use change as a system",
                "level": "Understand",
                "minutes": 8,
                "summary": "See why a single-cause explanation is rarely enough.",
                "body": (
                    "Land-use change rarely has a single cause. Economic pressures, policy signals, "
                    "technology and climate conditions, and social factors such as values and trust "
                    "can interact differently for different actors and places."
                ),
                "theory_cards": [
                    card(
                        "There is rarely one cause",
                        "Land-use change usually emerges from a bundle of pressures and conditions rather than a single driver.",
                        "Start here",
                    ),
                    card(
                        "Drivers interact",
                        "Economic pressures, policy signals, technology and climate, and people, values and trust can reinforce or counteract each other.",
                        "System view",
                    ),
                    card(
                        "Context changes what matters",
                        "The same driver can matter differently for different actors, places and conditions. That is why a generic list of drivers is not enough.",
                        "Actor and place",
                    ),
                    card(
                        "Ask a diagnostic question",
                        "Which drivers matter for which actor, in which place, under which conditions? This turns a list into an explanation you can act on.",
                        "Use it",
                    ),
                ],
                "takeaway": "Do not only list drivers. Look for how they interact, for whom, and under which conditions.",
                "prompt": "Think of one land-use decision you know. Which two or three drivers appear to interact?",
                "quiz": {
                    "question": "Which statement best matches the MOSAIC framing?",
                    "options": [
                        "Land-use change is mainly explained by financial incentives.",
                        "Land-use change usually emerges from interacting drivers that vary by actor and place.",
                        "Technology is normally the decisive driver of land-use change.",
                    ],
                    "answer": 1,
                    "explanation": "The learning page emphasizes interacting drivers and the importance of actor, place, and conditions.",
                },
            },
            {
                "id": "actors-and-place",
                "title": "What types of drivers exist?",
                "level": "Understand",
                "minutes": 7,
                "summary": "A summary of different types of drivers and examples of each.",
                "body": (
                    "The same incentive or regulation can be experienced differently by farmers, landowners, "
                    "municipalities, developers, conservation actors, and local communities."
                ),
                "theory_cards": [
                    card("Start with the actor", "A useful diagnosis asks who is actually making or influencing the land-use decision.", "Actor"),
                    card("Then locate the decision", "Place matters because markets, infrastructure, regulation, social relations and environmental conditions vary.", "Place"),
                    card("Then ask about conditions", "Risk, timing, trust, identity, resources and institutional context can change how the same policy or incentive is experienced.", "Conditions"),
                ],
                "takeaway": "A driver only becomes useful for analysis when it is connected to an actor, a place, and a context.",
                "prompt": "Choose one actor group. What could make the same policy attractive in one place but unattractive in another?",
                "quiz": None,
            },
            {
                "id": "implementation-gap",
                "title": "From high-level targets to local decisions",
                "level": "Apply",
                "minutes": 10,
                "summary": "Connect sustainability targets to the realities that shape implementation.",
                "body": (
                    "High-level goals often depend on local decisions. Implementation can be weakened by regulatory complexity, "
                    "bureaucratic burden, weak alignment across levels, or incentives that unintentionally discourage sustainable practices."
                ),
                "theory_cards": [
                    card("Targets depend on local decisions", "Climate, biodiversity, food, water, landscape and energy goals often depend on farmers, landowners, municipalities, developers, conservation actors and communities.", "From goals to action"),
                    card("Implementation gaps have structure", "Regulatory complexity, bureaucratic burdens, weak cross-scale alignment and badly aligned incentives can widen the gap between a target and what happens locally.", "Implementation"),
                    card("Viability can be necessary but insufficient", "Financial incentives may open the door, while uptake can still depend on trust, autonomy, identity, place attachment, risk, succession, social networks and perceived fit with reality.", "Beyond money"),
                ],
                "takeaway": "Economic viability can open the door, but uptake can also depend on trust, autonomy, identity, place attachment, risk, succession, social networks, and fit with local reality.",
                "prompt": "Where does an implementation gap appear in your own policy, research, or field context?",
                "tool": {
                    "id": "causal-loop-diagram",
                    "name": "Causal loop diagram (CLD)",
                    "description": "Map the variables behind a land-use decision, connect causes and effects, and mark whether each relationship moves in the same or opposite direction.",
                },
                "quiz": {
                    "question": "Why may a financial incentive be insufficient on its own?",
                    "options": [
                        "Because economic viability never matters.",
                        "Because uptake can also depend on trust, autonomy, identity, risk, social networks, and fit with local reality.",
                        "Because regulation always overrides local decisions.",
                    ],
                    "answer": 1,
                    "explanation": "The source describes economic viability as often necessary, but not sufficient.",
                },
            },
            {
                "id": "communicate-case",
                "title": "Communicate a convincing case",
                "level": "Convince",
                "minutes": 10,
                "summary": "Turn a systems diagnosis into a clear, actor-aware argument.",
                "body": (
                    "A convincing explanation connects the proposed change to the actor's reality. Use evidence, examples, "
                    "and language that make the interaction between drivers clear rather than presenting a single-cause story."
                ),
                "theory_cards": [
                    card("Start from the actor's reality", "Do not assume the same argument will work for every actor. Connect the proposed change to the pressures, motivations and constraints they actually face.", "Relevance"),
                    card("Explain the interaction", "A stronger case shows why several drivers reinforce or block one another instead of relying on a single-cause story.", "Explanation"),
                    card("Make the change make sense", "The goal is not only to say what should change, but why the change can fit the actor's reality under the conditions they face.", "Convince"),
                ],
                "takeaway": "The strongest case explains not just what should change, but why the change makes sense in the actor's reality.",
                "prompt": "Write one sentence explaining a proposed land-use change to a specific actor without assuming that money is the only concern.",
                "quiz": None,
            },
        ],
    },
    "future-pathways": {
        "title": "Future Pathways towards Sustainable Land-Use Futures",
        "short_title": "Future Pathways",
        "track": "Empowerment",
        "track_icon": "↝",
        "description": (
            "Move from a desirable nature-positive land-use future to practical pathways and regionally relevant action."
        ),
        "estimated_minutes": 63,
        "status": "Available",
        "eyebrow": "From vision to pathways and regional relevance",
        "source_note": (
            "This learning journey draws primarily on MOSAIC Deliverable D4.1: "
            "A comprehensive set of normative (policy) and exploratory scenarios for the case studies."
        ),
        "learning_outcomes": [
            "Understand what a nature-positive vision is.",
            "Use the Nature Futures Framework to work with different ways of valuing nature.",
            "Create a vision either from scratch through participatory visioning or from pre-defined policy objectives.",
            "Develop pathways from a shared vision towards transformations and action.",
            "Contextualise pathways into place-specific priorities and policy options.",
        ],
        "topics": [
            {
                "id": "nature-positive-futures",
                "title": "Why start with a nature-positive future?",
                "level": "Understand",
                "minutes": 9,
                "summary": "Learn why a normative future provides direction for systemic land-use change.",
                "body": (
                    "A nature-positive future begins with what people want to create, then connects that shared destination "
                    "to pathways and regionally relevant action."
                ),
                "theory_cards": [
                    card(
                        "Environmental challenges require systemic change",
                        "Biodiversity loss, climate change, declining ecosystem health and increasing pressure on natural resources cannot be solved through isolated measures or incremental improvements alone. They require long-term, systemic change in the way people interact with nature.",
                        "Why futures",
                    ),
                    card(
                        "Begin with a desirable future",
                        "Rather than asking what is likely to happen, a normative approach starts from the question: what kind of future do we want to create? It starts from a shared ambition and asks which transformations are needed to reach it.",
                        "Normative approach",
                    ),
                    card(
                        "A vision and a pathway do different jobs",
                        "A vision describes what a desirable future looks like and provides a shared destination. A pathway describes how that future can be reached through transformations, policies, governance changes, innovations and behavioural shifts over time.",
                        "Important distinction",
                    ),
                    card(
                        "The work moves through three connected steps",
                        "First create a shared vision of a desirable, nature-positive future. Then identify pathways that describe how it can be achieved, and finally contextualise those pathways to define concrete action for a specific place.",
                        "Learning sequence",
                    ),
                ],
                "takeaway": "A vision provides direction; pathways provide possible routes; contextualisation turns those routes into regionally relevant action.",
                "prompt": "Which future state would give direction to the land-use challenge you are working on, and why does it require more than incremental improvement?",
                "quiz": {
                    "question": "Which statement best describes the normative approach used in this module?",
                    "options": [
                        "It predicts the single future that is most likely to occur.",
                        "It begins with a desirable future and asks what transformations could lead towards it.",
                        "It focuses only on actions that fit within present-day constraints.",
                    ],
                    "answer": 1,
                    "explanation": "The normative approach begins with a shared ambition and works backwards towards the transformations and pathways needed to reach it.",
                },
                "self_check": [
                    "I can explain the difference between a vision and a pathway.",
                    "I can describe why a desirable future can strengthen agency and participation.",
                ],
            },
            {
                "id": "nature-futures-framework",
                "title": "The Nature Futures Framework",
                "level": "Understand",
                "minutes": 9,
                "summary": "Understand how three value perspectives create a plural space of desirable nature-positive futures.",
                "body": (
                    "The Nature Futures Framework is a flexible compass for developing desirable futures for people, nature and Mother Earth."
                ),
                "theory_cards": [
                    card(
                        "The framework is a compass, not one prescribed future",
                        "Developed under IPBES, the Nature Futures Framework supports visions of desirable, nature-positive futures and the pathways needed to achieve them. It recognises that societies, cultures and stakeholders value nature in different ways.",
                        "Purpose",
                    ),
                    card(
                        "Nature for Nature",
                        "This perspective emphasises nature's intrinsic value: the diversity of species, habitats, ecosystems and processes, and nature's ability to function autonomously.",
                        "Value perspective",
                    ),
                    card(
                        "Nature as Culture",
                        "This perspective highlights relational values, where societies, cultures, traditions and faiths are intertwined with nature in shaping diverse biocultural landscapes.",
                        "Value perspective",
                    ),
                    card(
                        "Nature for Society",
                        "This perspective highlights the utilitarian benefits and instrumental values that nature provides to people and societies.",
                        "Value perspective",
                    ),
                    card(
                        "The triangle represents mixtures of values",
                        "Activities and future visions can sit at a corner or combine the three perspectives. The framework makes plurality visible without requiring every person or place to value nature in the same way.",
                        "How to read it",
                    ),
                ],
                "takeaway": "The Nature Futures Framework creates space for different human-nature relationships while keeping every future nature-positive.",
                "practice_note": "Several MOSAIC Policy Labs used the Nature Futures Framework as reference perspectives for a nature-positive European land system.",
                "prompt": "Which of the three value perspectives is most visible in your current policy or project, and which perspective receives less attention?",
                "quiz": {
                    "question": "What does a position between the corners of the Nature Futures Framework triangle represent?",
                    "options": [
                        "A future that does not value nature.",
                        "A combination of Nature for Nature, Nature as Culture and Nature for Society perspectives.",
                        "A ranking in which one perspective is objectively better than the others.",
                    ],
                    "answer": 1,
                    "explanation": "The triangle represents different mixes of the three value perspectives rather than a ranking or a requirement to select one corner.",
                },
                "self_check": [
                    "I can distinguish the three Nature Futures Framework perspectives.",
                    "I understand why different value perspectives can lead to different pathways.",
                ],
            },
            {
                "id": "create-vision",
                "title": "Create a vision from scratch",
                "level": "Apply",
                "minutes": 9,
                "summary": "Co-create a desirable future through a participatory visioning process.",
                "body": (
                    "An appealing and inspiring vision can initiate a change trajectory towards a more sustainable future, society or system."
                ),
                "theory_cards": [
                    card(
                        "Describe the future state before the route",
                        "Create a narrative, image or other description of a desirable future state. Make the desires, assumptions, beliefs and paradigms underpinning that future explicit before deciding how to reach it.",
                        "Step 1",
                    ),
                    card(
                        "Choose a useful time horizon",
                        "Set the vision far enough away to escape today's constraints and avoid incremental thinking, yet close enough to remain imaginable and actionable. A horizon around 2050 can balance transformational thinking with relevance for current policy, planning and action.",
                        "Step 2",
                    ),
                    card(
                        "Co-create the vision through participatory visioning",
                        "Develop the nature-positive future with the people involved rather than starting from a pre-defined policy target. Use a participatory visioning process to contextualise the future and build a shared image of where the transition should lead.",
                        "Step 3",
                    ),
                    card(
                        "Use the framework to keep nature and people central",
                        "Use the three Nature Futures Framework perspectives to explore the desired ecological, social and economic characteristics of the future and to connect the vision to its underpinning value expressions.",
                        "Step 4",
                    ),
                    card(
                        "Build trust and motivation into the process",
                        "Create early dialogue between researchers and policymakers to address different priorities and professional cultures. Align the work with the personal ambitions of core team members so that people see a clear connection between their goals and the shared mission.",
                        "Take into account",
                    ),
                ],
                "takeaway": "A useful vision is desirable, shared, explicit about its values, and far enough away to enable transformational thinking without losing relevance for action.",
                "prompt": "Starting without a pre-defined policy target, write one or two sentences describing the desirable future state for your context. Whose desires, assumptions, beliefs and values need to shape it?",
                "tool": {
                    "id": "nature-positive-vision",
                    "name": "Vision from scratch canvas",
                    "description": "Co-create the future state, time horizon, value perspectives, participants and assumptions that shape the vision.",
                },
                "quiz": None,
                "self_check": [
                    "The vision is far enough away to move beyond today's constraints but remains imaginable.",
                    "The process makes values, assumptions and represented voices explicit.",
                    "The vision keeps nature and people at the centre.",
                ],
            },
            {
                "id": "vision-from-policy-objectives",
                "title": "Create a vision from EU policy objectives",
                "level": "Apply",
                "minutes": 9,
                "summary": "Use existing, negotiated policy targets as a shared nature-positive vision.",
                "body": (
                    "Long-term policy objectives can act as participatory positive visions that were developed and negotiated in a real-world setting."
                ),
                "theory_cards": [
                    card(
                        "Start from the existing policy landscape",
                        "Identify the frameworks for sustainable transformation and transition that shape the relevant regional, national and international policy landscape. Focus on the objectives that are relevant to the land system and the challenge being addressed.",
                        "Step 1",
                    ),
                    card(
                        "Select negotiated policy targets",
                        "Use existing policy targets that have been developed and negotiated amongst a wide range of actors. Treat long-term objectives as participatory positive visions to be achieved, rather than beginning with a new visioning process.",
                        "Step 2",
                    ),
                    card(
                        "Identify and categorise the objectives",
                        "Build the policy-objective-based vision through a multi-step process that identifies and categorises relevant objectives in the policy landscape. Make their time horizons and intended changes visible.",
                        "Step 3",
                    ),
                    card(
                        "Translate the objectives into a future state",
                        "Bring the selected objectives together as a coherent description of a nature-positive land system. Use the Nature Futures Framework to keep nature and people at the centre and connect the envisioned future to its underpinning value expressions.",
                        "Step 4",
                    ),
                    card(
                        "Keep the distinction between targets and pathways clear",
                        "The policy objectives describe the future to be achieved. The transformations, measures and actions that lead towards that future belong to the pathway and are developed in the next part.",
                        "Take into account",
                    ),
                ],
                "takeaway": "A policy-objective-based vision uses negotiated long-term targets as the shared destination, then makes their combined nature-positive future explicit before pathways are developed.",
                "practice_note": "The European Policy Lab in MOSAIC used existing, negotiated EU policy targets as a shared vision and identified and categorised policy objectives relevant to the European land system.",
                "prompt": "Which EU policy objectives are relevant to your land-use challenge, and what shared future state do they describe when considered together?",
                "tool": {
                    "id": "policy-objective-vision",
                    "name": "Policy-objective vision canvas",
                    "description": "Identify and categorise relevant EU policy objectives and translate them into a coherent shared vision.",
                },
                "quiz": {
                    "question": "What distinguishes a policy-objective-based vision from a vision created from scratch?",
                    "options": [
                        "It uses existing, negotiated long-term policy targets as the shared future to be achieved.",
                        "It begins by listing actions without defining a future state.",
                        "It replaces participation with a prediction of the most likely future.",
                    ],
                    "answer": 0,
                    "explanation": "This route begins with existing, negotiated policy targets and brings them together as a shared positive vision before developing pathways.",
                },
                "self_check": [
                    "The relevant policy objectives and time horizons have been identified.",
                    "The objectives have been categorised and combined into a coherent future state.",
                    "The vision remains distinct from the measures and actions that form its pathways.",
                ],
            },
            {
                "id": "create-pathways",
                "title": "Develop pathways towards the vision",
                "level": "Apply",
                "minutes": 15,
                "summary": "Translate the vision into several coherent sequences of transformations, actions and decisions.",
                "body": (
                    "Pathways move the process from a desirable destination to the transformations and actions that could make it possible."
                ),
                "theory_cards": [
                    card(
                        "Start from the vision and ask how to get there",
                        "Describe concrete actions and measures that underpin future changes. Do not assume there is only one roadmap: several pathways can reveal different trajectories and trade-offs between actions and measures.",
                        "Step 1",
                    ),
                    card(
                        "Construct a pathway through each value lens",
                        "Use Nature for Nature, Nature as Culture and Nature for Society to create distinct pathway narratives towards the same vision or policy objective. Each lens can reveal different land-management strategies and sets of transformations.",
                        "Step 2",
                    ),
                    card(
                        "Ask what must change",
                        "For Nature for Nature, ask what transformations enable nature itself to flourish. For Nature for Society, ask what enables people to benefit from and contribute to nature. For Nature as Culture, ask what must change in relationships, responsibilities and identities connected to nature.",
                        "Step 3",
                    ),
                    card(
                        "Make the pathway specific enough to use",
                        "Describe the transformations, policies, governance changes, innovations and behavioural shifts needed over time. Where relevant, specify temporal and spatial scales, land-use and land-cover types, and the actions that change indicators or biophysical properties.",
                        "Step 4",
                    ),
                    card(
                        "Review logic, consistency and suitability",
                        "Check the pathway narratives for logic, consistency and alignment with the three perspectives. Expert pathway development requires understanding of policy objectives, systems thinking and land-use change dynamics, so it may be less suitable as a first exercise for general stakeholders.",
                        "Take into account",
                    ),
                ],
                "takeaway": "Multiple pathways connect the same future vision to different transformations and make value choices, alternatives and trade-offs visible.",
                "practice_note": "MOSAIC researchers translated EU policy objectives into a nature-positive vision, developed pathway narratives through all three lenses in an expert workshop, clustered the narratives into broader pathways, and reviewed them for logic and consistency.",
                "prompt": "Choose one vision or policy objective. What would need to change if each Nature Futures Framework lens were taken seriously?",
                "tool": {
                    "id": "nff-pathway-builder",
                    "name": "NFF pathway builder",
                    "description": "Develop three pathway narratives towards the same vision and compare their transformations, actions and trade-offs.",
                },
                "quiz": {
                    "question": "Why create several pathways towards the same vision?",
                    "options": [
                        "To identify the one perspective that every stakeholder must accept.",
                        "To visualise different trajectories and reveal transformations and trade-offs.",
                        "To replace the future vision with a list of present-day problems.",
                    ],
                    "answer": 1,
                    "explanation": "Several pathways make alternative trajectories, value choices, transformations and trade-offs visible while working towards the same future vision.",
                },
                "self_check": [
                    "Each pathway is connected to the same future vision or policy objective.",
                    "The narratives describe changes over time rather than isolated actions.",
                    "The pathways are checked for logic, consistency and alignment with their value lens.",
                ],
            },
            {
                "id": "regional-relevance",
                "title": "Make pathways regionally relevant",
                "level": "Apply",
                "minutes": 12,
                "summary": "Work with stakeholders to retain, adapt or reconsider pathway elements for a specific place and implementation context.",
                "body": (
                    "Strategic pathways only become actionable when they are connected to regional priorities, opportunities and constraints."
                ),
                "theory_cards": [
                    card(
                        "Begin with the implementation context",
                        "Ask which combination of pathways is most relevant to the people, place and implementation context involved. Consider landscapes, institutions, cultures, livelihoods, governance arrangements and practical constraints.",
                        "Step 1",
                    ),
                    card(
                        "Let stakeholders position their priorities",
                        "Use the Nature Futures Framework triangle to show how strongly implementation priorities align with Nature for Nature, Nature as Culture, Nature for Society or a combination of the three.",
                        "Step 2",
                    ),
                    card(
                        "Treat the result as a conversation, not a vote",
                        "A point between the corners represents a combination of value perspectives. Look for where priorities converge or differ instead of selecting one pathway and discarding the others.",
                        "Step 3",
                    ),
                    card(
                        "Retain, adapt or reconsider pathway elements",
                        "Compare stakeholder priorities with the expert-developed pathways. Decide which elements remain relevant, which need adjustment for local conditions, and which should be reconsidered before defining concrete action, governance changes and investment.",
                        "Step 4",
                    ),
                    card(
                        "Check how place changes the route",
                        "The same policy target can produce very different pathways in different regions. Make local ecological conditions, cultural traditions, policy responsibilities, costs, benefits and opportunities explicit before moving to implementation.",
                        "Take into account",
                    ),
                ],
                "takeaway": "Regional relevance comes from combining value perspectives and adapting strategic pathways to the people, place and practical conditions involved.",
                "practice_note": "In Portugal, stakeholders connected EU objectives to local nurseries, watercourses, soils, traditional farming and suitable renewable-energy locations. In Denmark, the same afforestation target produced different priorities for biodiversity, recreation, groundwater protection and cost-effective climate mitigation.",
                "prompt": "Which pathway elements would your stakeholders retain, adapt or reconsider, and which local conditions explain those choices?",
                "tool": {
                    "id": "regional-pathway-canvas",
                    "name": "Regional pathway canvas",
                    "description": "Compare stakeholder priorities, local conditions and pathway elements before defining place-specific action.",
                },
                "quiz": {
                    "question": "What is the purpose of placing stakeholder priorities in the Nature Futures Framework triangle?",
                    "options": [
                        "To vote for one pathway and discard the others.",
                        "To understand combinations of values, convergence and differences that should shape adaptation.",
                        "To prove that every region should implement the same EU-level pathway.",
                    ],
                    "answer": 1,
                    "explanation": "The distribution helps a group understand combined value perspectives, convergence and differences, and what should be retained, adapted or reconsidered.",
                },
                "self_check": [
                    "Relevant landscapes, institutions, cultures, livelihoods and constraints are visible.",
                    "Stakeholder differences are used to improve pathways rather than reduced to a single vote.",
                    "The final actions remain connected to the long-term nature-positive vision.",
                ],
            },
        ],
    },
}


# Convince is deliberately modelled as a resource/evidence hub rather than a
# required linear lesson. This mirrors the MOSAIC Learn source pages: Understand
# teaches concepts, Apply supports use in practice, while Convince brings together
# arguments, examples, evidence and communication resources.
MODULES["policy-lab"]["convince"] = {
    "title": "Make the case for a Policy Lab",
    "intro": (
        "Use this space when you need to explain, justify or advocate for a Policy Lab in a project, "
        "organisation or policy programme. Browse evidence, practice examples and communication assets rather than completing another lesson."
    ),
    "why": [
        {
            "title": "Create shared ownership",
            "text": "Policy Labs give researchers, policymakers and stakeholders a structured space to explore a shared challenge and shape options together.",
            "accent": "green",
        },
        {
            "title": "Work with complexity",
            "text": "They are useful where land-use choices involve competing interests, uncertainty and long-term trade-offs that are difficult to handle through linear consultation alone.",
            "accent": "blue",
        },
        {
            "title": "Connect evidence to decisions",
            "text": "The value is not participation for its own sake: the process links research, stakeholder knowledge and real policy windows to produce more actionable options.",
            "accent": "ochre",
        },
    ],
    "examples": [
        {
            "place": "Belgium",
            "title": "Local involvement strengthened commitment",
            "text": "The Belgian Policy Lab found that involving local actors early helped create enthusiasm, ownership and practical input into how the process was organised.",
            "lesson": "Invite people into shaping the process, not only into reacting to it.",
        },
        {
            "place": "Belgium",
            "title": "Existing momentum can be an asset",
            "text": "The Policy Lab could build on relationships and collaboration that already existed around the Landscape Park, giving the new process a stronger starting point.",
            "lesson": "Map the networks and collaborations you can build on before creating new structures.",
        },
        {
            "place": "Portugal",
            "title": "Interactive formats still need trust",
            "text": "Online interactive moments did not automatically lead to open participation. The experience highlighted the importance of trust, facilitation and informal connection.",
            "lesson": "Participation is designed through relationships and facilitation, not only through tools.",
        },
    ],
    "audiences": {
        "Policy advocacy": {
            "headline": "Show why a Policy Lab can strengthen a programme or funding call",
            "text": "Emphasise the value of structured co-production where competing interests and uncertainty make ordinary consultation insufficient.",
            "use": ["Decision rationale", "Pitch deck", "Examples from practice"],
        },
        "Policy workers": {
            "headline": "Connect the method to a real decision process",
            "text": "Focus on how a Policy Lab can align evidence, stakeholder knowledge and policy timing around an actionable challenge.",
            "use": ["Policy brief", "Argument library", "Policy-window examples"],
        },
        "Practitioners": {
            "headline": "Make the role of land managers and local actors visible",
            "text": "Use concrete examples to show how practitioner knowledge can shape problem framing, options and implementation rather than being consulted only at the end.",
            "use": ["Practice examples", "Participant experiences", "Stakeholder guidance"],
        },
        "Academics": {
            "headline": "Explain how participation contributes to impact",
            "text": "Position Policy Labs as a structured science-policy interface that can connect research questions and evidence to real decision processes and stakeholder experience.",
            "use": ["Evidence sheet", "Case studies", "Method description"],
        },
    },
    "resources": [
        {"type": "Policy brief", "title": "Policy Labs for Land-Use Change", "description": "A short, advocacy-ready explanation of why and when to use a Policy Lab.", "status": "Connect existing MOSAIC PDF"},
        {"type": "Pitch deck", "title": "Explaining the Policy Lab approach", "description": "Slides for presenting the approach to partners, funders or decision-makers.", "status": "Connect existing MOSAIC PDF"},
        {"type": "Evidence sheet", "title": "Impact & evidence", "description": "A compact evidence resource for people who need the rationale and practice lessons quickly.", "status": "Connect existing MOSAIC PDF"},
        {"type": "Source", "title": "MOSAIC Deliverable D2.1", "description": "The underlying guidance for establishing a Policy Lab and the six building blocks used in this prototype.", "status": "Link source deliverable"},
    ],
    "pitch": (
        "Policy Labs create a structured space where policy, research and stakeholder knowledge can meet around a real decision challenge. "
        "They help turn complex land-use issues into shared understanding, practical options and action that fits the policy context."
    ),
    "author_source_url": "https://coda.io/d/_dtYXixv6BDC/Convince_suUWcwgU",
}

MODULES["drivers"]["convince"] = {
    "title": "Make the case for analysing drivers",
    "intro": (
        "Use this space when you need to explain why driver analysis matters, show what MOSAIC found in practice, "
        "or equip someone else with a brief, example or argument. It is a resource library, not another required lesson."
    ),
    "why": [
        {
            "title": "Move beyond symptoms",
            "text": "Driver analysis helps reveal the interacting social, economic, environmental, technological and political forces underneath visible land-use outcomes.",
            "accent": "blue",
        },
        {
            "title": "Design interventions that fit reality",
            "text": "Understanding which drivers matter for which actors makes it easier to see why a technically sound or financially supported measure may still be rejected or ignored.",
            "accent": "green",
        },
        {
            "title": "Anticipate trade-offs and future change",
            "text": "A systems view helps identify interactions, uncertainties and potential leverage points instead of assuming one policy instrument will work everywhere.",
            "accent": "ochre",
        },
    ],
    "examples": [
        {
            "place": "Belgium",
            "title": "Grassland decline in the Vlaamse Ardennen",
            "text": "Profitability, regulation, administrative burden, labour, mechanisation, succession and changing recreational land users interacted in the grassland system.",
            "lesson": "A biodiversity outcome can have economic, institutional, technological and social causes at the same time.",
        },
        {
            "place": "Portugal",
            "title": "A two-speed landscape transformation",
            "text": "Irrigation infrastructure, capital, drought, policy support, global markets, abandonment, identity and heritage helped explain simultaneous intensification and decline of traditional systems.",
            "lesson": "The same landscape can contain contrasting trajectories driven by different combinations of forces.",
        },
        {
            "place": "Denmark",
            "title": "Why compensation alone may not trigger afforestation",
            "text": "Landowners also weighed permanence, inheritance, autonomy, uncertainty, land prices and opportunity costs when considering voluntary afforestation.",
            "lesson": "Financial viability can matter without being the whole decision.",
        },
        {
            "place": "Switzerland",
            "title": "Renewable energy in Alpine landscapes",
            "text": "National energy goals interacted with local acceptance, landscape identity, tourism, biodiversity and emotional responses to large-scale photovoltaic development.",
            "lesson": "Technical suitability does not automatically create social acceptance.",
        },
    ],
    "audiences": {
        "Policy advocacy": {
            "headline": "Connect visible problems to underlying causes",
            "text": "Use driver analysis to strengthen campaigns and recommendations by showing why outcomes persist and which forces need to change together.",
            "use": ["Argument library", "Policy brief", "MOSAIC examples"],
        },
        "Policy workers": {
            "headline": "Shift from choosing instruments to understanding what must change",
            "text": "Ask which driver a policy is intended to influence, for which actor, in which place and under what conditions before assuming the instrument will translate into uptake.",
            "use": ["Impact sheet", "Decision tool", "Actor-specific examples"],
        },
        "Practitioners": {
            "headline": "Show why local decisions are more than a response to incentives",
            "text": "Use practice examples to make risk, trust, autonomy, identity, family considerations and local conditions visible alongside economics and regulation.",
            "use": ["Practical guide", "Field examples", "Reflection prompts"],
        },
        "Academics": {
            "headline": "Use systems thinking to explain interactions and leverage points",
            "text": "Frame driver analysis as a way to move beyond isolated variables and develop richer explanations of land-use dynamics and behavioural responses.",
            "use": ["D3.1", "Case studies", "Systems-thinking resources"],
        },
    },
    "resources": [
        {"type": "Policy brief", "title": "Why identify drivers of land-use change?", "description": "A short explanation for policy and advocacy audiences.", "status": "Connect existing MOSAIC PDF"},
        {"type": "Pitch deck", "title": "Drivers of Change", "description": "A concise visual story for explaining the driver approach to partners and stakeholders.", "status": "Connect existing MOSAIC PDF"},
        {"type": "Evidence sheet", "title": "Impact & evidence", "description": "A quick reference on what driver analysis can add to policy, research and practice.", "status": "Connect existing MOSAIC PDF"},
        {"type": "Source", "title": "MOSAIC Deliverable D3.1", "description": "Identifying drivers of land-use change - the main evidence base for this learning journey.", "status": "Link source deliverable"},
    ],
    "pitch": (
        "Land-use change is rarely driven by one cause. Driver analysis helps us understand how economic pressures, policy signals, technologies, climate conditions, "
        "values, trust and identity interact for different actors and places - so interventions can target causes rather than symptoms."
    ),
    "author_source_url": "https://coda.io/d/_dtYXixv6BDC/Convince-under-construction_su_36hW4",
}

# -----------------------------------------------------------------------------
# TOOL DOWNLOAD FILES - EDIT THIS SECTION
# -----------------------------------------------------------------------------
# 1. Put each .docx or .pdf file in: assets/tools/
# 2. Add only its filename to the matching list below.
# 3. You may add a Word file, a PDF, or both. The app creates the buttons.
#
# Example:
# "causal-loop-diagram": ["causal-loop-diagram.docx", "causal-loop-diagram.pdf"],
TOOL_DOWNLOAD_FILES = {
    "causal-loop-diagram": [],
    "nature-positive-vision": [],
    "policy-objective-vision": [],
    "nff-pathway-builder": [],
    "regional-pathway-canvas": [],
    "finding-your-focus": [],
    "define-core-group": [],
    "policy-mapping": [],
    "stakeholder-analysis": [],
    "timeline-workshop": [],
    "30-second-message": [],
}


TOOL_DEFINITIONS = {
    "causal-loop-diagram": {
        "title": "Causal loop diagram (CLD)",
        "module_id": "drivers",
        "topic_id": "implementation-gap",
        "duration": "20–30 min",
        "format": "Interactive diagram",
        "description": (
            "Turn a list of drivers into a system map. Add variables, connect causes and effects, "
            "and label whether each relationship moves in the same (+) or opposite (-) direction."
        ),
        "outcome": "A downloadable causal-loop diagram and a short leverage-point reflection.",
        "steps": [
            "Name the decision or land-use outcome at the centre of the analysis.",
            "Add concrete variables that can increase or decrease over time.",
            "Connect variables, assign polarity, and look for feedback loops or leverage points.",
        ],
        "kind": "cld",
    },
    "nature-positive-vision": {
        "title": "Vision from scratch canvas",
        "module_id": "future-pathways",
        "topic_id": "create-vision",
        "duration": "30–45 min",
        "format": "Vision canvas",
        "description": (
            "Co-create a desirable future state through participatory visioning and make its values and assumptions explicit."
        ),
        "outcome": "A concise nature-positive vision with a time horizon, represented perspectives and clear assumptions.",
        "steps": [
            "Describe the desirable ecological, social and economic characteristics of the future state.",
            "Use the three Nature Futures Framework perspectives to make value choices and missing voices visible.",
            "Check that the horizon enables transformational thinking while remaining relevant for action, and build shared ownership through participation.",
        ],
        "prompts": [
            ("Future state", "What does the desirable nature-positive future look like?"),
            ("Time horizon", "Which horizon is far enough to escape today's constraints but close enough to remain actionable?"),
            ("Values and perspectives", "How are Nature for Nature, Nature as Culture and Nature for Society represented?"),
            ("Participation and assumptions", "Who should shape the vision, and which desires, assumptions, beliefs or paradigms must be explicit?"),
        ],
    },
    "policy-objective-vision": {
        "title": "Policy-objective vision canvas",
        "module_id": "future-pathways",
        "topic_id": "vision-from-policy-objectives",
        "duration": "30–45 min",
        "format": "Policy-objective mapping canvas",
        "description": (
            "Use existing, negotiated EU policy targets as a shared positive vision for a nature-positive land system."
        ),
        "outcome": "A coherent future state built from identified and categorised policy objectives.",
        "steps": [
            "Identify the regional, national and EU policy frameworks relevant to the land-use challenge.",
            "Select and categorise the long-term objectives that describe the future to be achieved.",
            "Bring the objectives together as a coherent nature-positive vision before defining pathways or actions.",
        ],
        "prompts": [
            ("Policy landscape", "Which frameworks for sustainable transformation and transition shape this land-use challenge?"),
            ("Relevant objectives", "Which negotiated EU policy objectives and time horizons are relevant to the land system?"),
            ("Categories and relationships", "How can the objectives be categorised, and where do they reinforce or depend on one another?"),
            ("Shared future state", "What nature-positive future do these objectives describe when considered together?"),
            ("Boundary with pathways", "Which statements describe the future destination, and which measures or actions should be developed later as pathways?"),
        ],
    },
    "nff-pathway-builder": {
        "title": "NFF pathway builder",
        "module_id": "future-pathways",
        "topic_id": "create-pathways",
        "duration": "45–60 min",
        "format": "Pathway comparison",
        "description": (
            "Create several routes towards the same future vision by asking what must change through each Nature Futures Framework lens."
        ),
        "outcome": "Three comparable pathway narratives showing transformations, actions, timing and trade-offs.",
        "steps": [
            "Start with one shared vision or policy objective.",
            "Develop a pathway through each of the three Nature Futures Framework perspectives.",
            "Review the narratives for logic, consistency, trade-offs and alignment with their perspective.",
        ],
        "prompts": [
            ("Shared destination", "Which future vision or policy objective should every pathway work towards?"),
            ("Nature for Nature", "What transformations are needed for nature itself to flourish?"),
            ("Nature as Culture", "What must change in relationships, responsibilities and identities connected to nature?"),
            ("Nature for Society", "What transformations enable people to benefit from and contribute to nature?"),
            ("Sequence and trade-offs", "Which policies, governance changes, innovations and behavioural shifts are needed over time, and what trade-offs appear?"),
        ],
    },
    "regional-pathway-canvas": {
        "title": "Regional pathway canvas",
        "module_id": "future-pathways",
        "topic_id": "regional-relevance",
        "duration": "30–45 min",
        "format": "Contextualisation canvas",
        "description": (
            "Connect strategic pathways to stakeholder priorities, regional conditions and an actionable implementation context."
        ),
        "outcome": "A place-specific pathway showing what to retain, adapt or reconsider and why.",
        "steps": [
            "Map the people, place and implementation conditions that shape what is possible.",
            "Position stakeholder priorities in or between the three Nature Futures Framework perspectives.",
            "Use convergence and differences to retain, adapt or reconsider pathway elements.",
        ],
        "prompts": [
            ("Regional context", "Which landscapes, institutions, cultures, livelihoods, governance arrangements and constraints matter?"),
            ("Stakeholder priorities", "Where do priorities sit in the Nature Futures Framework triangle, and where do they converge or differ?"),
            ("Adaptation", "Which pathway elements should be retained, adapted or reconsidered for this place?"),
            ("Action", "Which concrete actions, governance changes and investments follow from the adapted pathway?"),
        ],
    },
    "finding-your-focus": {
        "title": "Finding Your Focus",
        "module_id": "policy-lab",
        "topic_id": "focus",
        "duration": "15–20 min",
        "format": "Guided worksheet",
        "description": "Find the overlap between a societal concern, a real policy opportunity, and a genuine knowledge need.",
        "outcome": "A one-sentence Core Focus with a clear reason to act now.",
        "steps": [
            "Describe each side of the focus triangle separately.",
            "Look for the overlap that matters to policy, research, and society.",
            "Write one shared focus and test whether it explains why action is timely.",
        ],
        "prompts": [
            ("Societal concern", "What is happening, who is affected, and why does it matter?"),
            ("Policy opportunity", "Which decision, revision, programme, or implementation moment creates an opening?"),
            ("Knowledge need", "What must be understood or tested before people can act with confidence?"),
            ("Core Focus", "Bring the three elements together in one sentence, including why this matters now."),
        ],
    },
    "define-core-group": {
        "title": "Define Your Core Group",
        "module_id": "policy-lab",
        "topic_id": "core-group",
        "duration": "20–30 min",
        "format": "Team canvas",
        "description": "Clarify the small steering team, the functions it must cover, and how the group will work together.",
        "outcome": "A practical Core Group brief covering people, roles, gaps, and working rhythm.",
        "steps": [
            "Start with the functions the group must perform, not a list of familiar names.",
            "Match people to roles and make bridging or facilitation responsibilities explicit.",
            "Agree how knowledge, decisions, and continuity will be maintained.",
        ],
        "prompts": [
            ("Core members", "Who needs to be in the small steering group, and what perspective does each person bring?"),
            ("Roles and responsibilities", "Who leads policy connections, research, facilitation, coordination, and knowledge brokering?"),
            ("Strengths and gaps", "What can this group already do well, and which missing profile or network could weaken it?"),
            ("Working rhythm", "How often will the group meet, decide, document, and bring in wider expertise?"),
        ],
    },
    "policy-mapping": {
        "title": "Policy Mapping",
        "module_id": "policy-lab",
        "topic_id": "policy-mapping",
        "duration": "30–45 min",
        "format": "Decision map",
        "description": "Locate relevant policies, institutions, actors, decision points, and timing around the shared challenge.",
        "outcome": "A focused map of where and when the Policy Lab can realistically influence a decision.",
        "steps": [
            "Choose one decision process that is central to the Core Focus.",
            "Map formal authority, informal influence, governance levels, and the current policy stage.",
            "Identify the next realistic entry point and what evidence or relationship it requires.",
        ],
        "prompts": [
            ("Policy process", "Which policy, plan, programme, or implementation process matters most?"),
            ("Decision landscape", "Who decides, who influences, and how do governance levels connect?"),
            ("Timing", "Where is the process now, and what is the next decision moment?"),
            ("Entry point", "Where could the Policy Lab make a useful contribution, with what evidence or interaction?"),
        ],
    },
    "stakeholder-analysis": {
        "title": "Stakeholder Analysis",
        "module_id": "policy-lab",
        "topic_id": "stakeholders",
        "duration": "30–45 min",
        "format": "Engagement canvas",
        "description": "Identify who is affected, influential, missing, or sceptical and decide how each should be involved.",
        "outcome": "A prioritised stakeholder picture and an initial engagement approach.",
        "steps": [
            "List stakeholders across policy, research, practice, markets, and civil society.",
            "Compare influence, interest, impact, stance, and whose voice is missing.",
            "Choose an appropriate role and next contact for the priority groups.",
        ],
        "prompts": [
            ("Stakeholder landscape", "Who is affected, who can influence the outcome, and who holds relevant knowledge?"),
            ("Priorities", "Which actors have high influence, high interest, high impact, or a critical missing perspective?"),
            ("Risks and relationships", "Who may be sceptical, over-consulted, hard to reach, or in conflict with others?"),
            ("Engagement plan", "Who should inform, advise, co-design, decide, or help deliver—and what is the next contact?"),
        ],
    },
    "timeline-workshop": {
        "title": "Timeline Workshop",
        "module_id": "policy-lab",
        "topic_id": "workplan",
        "duration": "30–45 min",
        "format": "Sequencing worksheet",
        "description": "Sequence policy deadlines, research tasks, and stakeholder interactions around real decision moments.",
        "outcome": "A coherent workplan with dependencies, pressure points, and gaps made visible.",
        "steps": [
            "Place fixed policy dates and institutional rhythms on the timeline first.",
            "Work backwards to position research outputs and stakeholder interactions.",
            "Sense-check dependencies, overload, quiet periods, and ownership.",
        ],
        "prompts": [
            ("Decision moments", "Which dates, windows, or institutional rhythms cannot move?"),
            ("Research milestones", "What knowledge must be ready, in which form, and by when?"),
            ("Stakeholder interactions", "Which conversations, workshops, or feedback moments must happen before decisions?"),
            ("Dependencies and risks", "What must happen first, where could the sequence fail, and who owns the response?"),
        ],
    },
    "30-second-message": {
        "title": "30-second message",
        "module_id": "policy-lab",
        "topic_id": "main-message",
        "duration": "10–15 min",
        "format": "Message builder",
        "description": "Shape a concise message around purpose, timing, contribution, audience relevance, and a clear ask.",
        "outcome": "A reusable short pitch plus the ingredients for an audience-specific version.",
        "steps": [
            "Choose one real audience and the one thing they should understand or do.",
            "Combine purpose, why now, the Policy Lab contribution, and a clear ask.",
            "Read it aloud, remove jargon, and adapt it for a second audience.",
        ],
        "prompts": [
            ("Audience", "Who are you speaking to, and what matters to them?"),
            ("Purpose and timing", "What is the challenge, and why does it need attention now?"),
            ("Contribution", "What will the Policy Lab make possible that is difficult today?"),
            ("Clear ask", "What specific contribution, decision, or next step do you want from this audience?"),
        ],
    },
}


ROLE_CALLOUTS = {
    "Policy / public administration": (
        "Focus on where policy signals, cross-scale alignment, decision windows and administrative burden shape implementation."
    ),
    "Research": (
        "Focus on how evidence connects to actor-specific mechanisms, policy timing and real decision processes."
    ),
    "Practice / land management": (
        "Focus on fit with local reality, risk, autonomy, trust, practical feasibility and meaningful participation."
    ),
    "Community / facilitation": (
        "Focus on relationships, values, identity, trust, power dynamics and whose perspective may be missing."
    ),
}
