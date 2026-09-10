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
                "tool": {"name": "Finding Your Focus", "description": "Use three prompts — societal concern, policy opportunity and knowledge need — to define a shared Core Focus."},
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
                "tool": {"name": "Define Your Core Group", "description": "Clarify strengths, roles, responsibilities, meeting rhythm and the profiles needed for functions such as policy lead and knowledge broker."},
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
                "tool": {"name": "Policy Mapping", "description": "Build a focused picture of relevant policies, actors, decision points and stages in the policy cycle."},
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
                "tool": {"name": "Stakeholder Analysis", "description": "Use influence, interest and other dimensions to identify, prioritise and revisit who should be involved and how."},
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
                "tool": {"name": "Timeline Workshop", "description": "Place policy deadlines and institutional rhythms first, then research milestones and stakeholder interactions, and sense-check the sequence for overload and gaps."},
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
                "tool": {"name": "30-second message", "description": "Draft one short message around purpose, timing, contribution and a clear ask, then adapt it for a second audience."},
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
                "title": "Which drivers matter for whom?",
                "level": "Understand",
                "minutes": 7,
                "summary": "Shift from a generic list of drivers to an actor- and place-specific diagnosis.",
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
        "title": "Exploring Future Pathways",
        "short_title": "Future Pathways",
        "track": "Empowerment",
        "track_icon": "↝",
        "description": (
            "A future module for exploring possible pathways and returning to the Policy Lab with sharper questions and options for action."
        ),
        "estimated_minutes": 40,
        "status": "Coming soon",
        "eyebrow": "From insight to action",
        "source_note": "Catalogue placeholder only in this prototype.",
        "learning_outcomes": [],
        "topics": [],
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
