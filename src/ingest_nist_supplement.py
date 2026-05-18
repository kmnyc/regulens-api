"""Ingest NIST AI RMF Playbook action descriptions as supplementary document.

Adds specific suggested actions for GOVERN, MAP, MEASURE, MANAGE subcategories
from publicly available NIST AI RMF Playbook (nvlpubs.nist.gov/nistpubs/ai/).

Run:
    python3 -m src.ingest_nist_supplement
"""
from __future__ import annotations
import hashlib, os, re, uuid
import psycopg2

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_wlvpsDzh78We@ep-gentle-glitter-aqzwfi7t.c-8.us-east-1.aws.neon.tech:5432/neondb?sslmode=require",
)

PLAYBOOK_CHUNKS: list[dict] = [
    # GOVERN pillar — suggested actions
    {
        "article_ref": "GOVERN 1 Actions",
        "section_path": ["GOVERN", "Policies_Processes_Culture"],
        "content": (
            "NIST AI RMF GOVERN 1 — Policies, processes, procedures, and practices across the organization related to the mapping, measuring, and managing of AI risks are in place, transparent, and implemented effectively. "
            "Suggested actions: Establish organizational AI risk governance policies defining risk tolerance and accountability. "
            "Document policies for identifying, assessing, and responding to AI risks throughout the lifecycle. "
            "Assign accountability for AI risk management outcomes to senior leadership. "
            "Ensure AI risk management policies are communicated to all relevant personnel. "
            "Review and update AI governance policies at least annually and after significant AI incidents. "
            "Integrate AI risk management requirements into project management and procurement processes."
        ),
    },
    {
        "article_ref": "GOVERN 2 Actions",
        "section_path": ["GOVERN", "Accountability_Culture"],
        "content": (
            "NIST AI RMF GOVERN 2 — Accountability structures for teams that develop, deploy, evaluate, and acquire AI systems are in place. "
            "Suggested actions: Define clear roles and responsibilities for AI development, deployment, and oversight teams. "
            "Establish accountability chains from AI system operators to senior leadership. "
            "Implement role-based access controls aligned with accountability structures. "
            "Document escalation procedures for AI risk decisions that exceed team authority. "
            "Conduct regular accountability reviews to verify roles are appropriately staffed and functioning. "
            "Ensure AI accountability structures include diverse perspectives including ethics, legal, and domain expertise."
        ),
    },
    {
        "article_ref": "GOVERN 3 Actions",
        "section_path": ["GOVERN", "Workforce_Diversity_Culture"],
        "content": (
            "NIST AI RMF GOVERN 3 — Organizational teams are committed to a culture that considers and communicates AI risk. "
            "Suggested actions: Promote psychological safety for AI risk reporting — staff must feel comfortable raising concerns. "
            "Include AI ethics and risk awareness in onboarding and regular training programs. "
            "Establish anonymous reporting channels for AI-related concerns. "
            "Recognize and reward responsible AI behavior in performance evaluations. "
            "Engage diverse teams including sociologists, ethicists, domain experts, and impacted community representatives. "
            "Conduct regular tabletop exercises or AI incident simulations to build organizational readiness."
        ),
    },
    {
        "article_ref": "GOVERN 4 Actions",
        "section_path": ["GOVERN", "Organizational_Teams"],
        "content": (
            "NIST AI RMF GOVERN 4 — Organizational teams are committed to a culture that considers and communicates AI risk. "
            "Suggested actions: Establish cross-functional AI risk review boards with representatives from engineering, legal, ethics, and business units. "
            "Define decision rights for AI deployment — who can approve, who can veto. "
            "Implement structured review processes for high-risk AI deployment decisions. "
            "Document dissenting views in AI deployment approval records. "
            "Create feedback loops from operational AI performance back to design and governance teams. "
            "Ensure AI risk culture extends to third-party AI vendors and partners through contractual requirements."
        ),
    },
    {
        "article_ref": "GOVERN 5 Actions",
        "section_path": ["GOVERN", "Policies_Organizational_Teams"],
        "content": (
            "NIST AI RMF GOVERN 5 — Organizational policies and practices are in place to foster a critical and open culture surrounding AI risk. "
            "Suggested actions: Establish AI ethics review boards or ombudspersons with genuine authority to influence decisions. "
            "Implement structured ethics impact assessments for new AI initiatives before resource commitment. "
            "Create mechanisms for external stakeholder input on AI system design and deployment. "
            "Publish transparency reports on AI system performance, incidents, and governance decisions. "
            "Define minimum documentation standards for all AI systems regardless of risk level. "
            "Ensure AI policies address emerging risks including generative AI, autonomous systems, and agentic applications."
        ),
    },
    {
        "article_ref": "GOVERN 6 Actions",
        "section_path": ["GOVERN", "Policies_Third_Party"],
        "content": (
            "NIST AI RMF GOVERN 6 — Policies and procedures are established for the responsible acquisition and use of AI from third-party entities. "
            "Suggested actions: Develop AI procurement standards requiring vendors to demonstrate responsible AI practices. "
            "Assess third-party AI systems against organizational risk tolerance before acquisition. "
            "Include AI-specific requirements in vendor contracts: documentation, audit rights, incident notification, change management. "
            "Maintain an inventory of third-party AI systems with associated risk classifications. "
            "Conduct periodic reassessment of third-party AI systems as part of vendor management. "
            "Establish off-boarding procedures for retiring third-party AI systems including data handling requirements."
        ),
    },
    # MAP pillar
    {
        "article_ref": "MAP 1 Actions",
        "section_path": ["MAP", "Context_Established"],
        "content": (
            "NIST AI RMF MAP 1 — Context is established and understood. "
            "Suggested actions: Define and document the AI system's intended purpose, context of use, and deployment environment before design begins. "
            "Identify the full range of stakeholders including developers, operators, users, and affected parties. "
            "Map the AI system to applicable laws, regulations, and standards (EU AI Act, sector-specific requirements). "
            "Characterize the risk level of the AI system using a documented classification methodology. "
            "Identify assumptions, constraints, and dependencies that affect AI system performance. "
            "Document the AI system's position in the broader sociotechnical system in which it operates."
        ),
    },
    {
        "article_ref": "MAP 2 Actions",
        "section_path": ["MAP", "Scientific_Research"],
        "content": (
            "NIST AI RMF MAP 2 — Scientific and technological aspects and impacts of AI systems are understood and considered. "
            "Suggested actions: Review relevant scientific literature and technical standards applicable to the AI approach being used. "
            "Assess model and algorithm selection for known limitations, failure modes, and documented biases. "
            "Evaluate training data quality, representativeness, and potential for encoding historical biases. "
            "Document technical limitations including distributional shift sensitivity, adversarial robustness, and interpretability constraints. "
            "Assess computational and environmental costs of AI system development and deployment. "
            "Stay current with emerging research on AI safety, fairness, and robustness relevant to the system's domain."
        ),
    },
    {
        "article_ref": "MAP 3 Actions",
        "section_path": ["MAP", "AI_Benefits_Costs"],
        "content": (
            "NIST AI RMF MAP 3 — AI risks and benefits are mapped and quantified to the extent possible. "
            "Suggested actions: Enumerate potential benefits of the AI system for each stakeholder group. "
            "Quantify expected harms using likelihood × severity × reversibility framework. "
            "Assess distributional impacts — do benefits and harms fall disproportionately on specific groups? "
            "Evaluate aggregate societal impact including systemic effects at scale. "
            "Document risk-benefit tradeoffs explicitly and subject them to stakeholder review. "
            "Track whether realized benefits match projected benefits post-deployment."
        ),
    },
    {
        "article_ref": "MAP 4 Actions",
        "section_path": ["MAP", "Risks_Identified"],
        "content": (
            "NIST AI RMF MAP 4 — Risks and benefits are identified for all parties involved. "
            "Suggested actions: Conduct structured risk identification workshops including technical, legal, ethics, and domain experts. "
            "Use risk taxonomies (e.g., NIST AI RMF risk categories) to ensure systematic coverage. "
            "Identify risks to: operators (liability, reputational), users (harm, privacy), third parties (discrimination), society (systemic effects). "
            "Document foreseeable misuse scenarios and assess risk of each. "
            "Assess compounding risks when multiple AI systems interact or share data. "
            "Update risk identification after incidents, performance monitoring alerts, or changes to deployment context."
        ),
    },
    {
        "article_ref": "MAP 5 Actions",
        "section_path": ["MAP", "Impacts_Documented"],
        "content": (
            "NIST AI RMF MAP 5 — Likelihood and impact of identified risks are evaluated. "
            "Suggested actions: Evaluate risk likelihood using historical incident data, expert judgment, and red-team exercises. "
            "Assess impact severity using scales that account for harm reversibility and affected population size. "
            "Prioritize risks using a risk matrix that drives resource allocation and treatment planning. "
            "Document risk evaluation rationale transparently — especially for risks judged low priority. "
            "Conduct sensitivity analysis to understand how risk estimates change under different assumptions. "
            "Review and update risk evaluations at defined intervals and after significant system changes."
        ),
    },
    # MEASURE pillar
    {
        "article_ref": "MEASURE 1 Actions",
        "section_path": ["MEASURE", "Measurement_Approaches"],
        "content": (
            "NIST AI RMF MEASURE 1 — AI risk measurement approaches are identified and applied. "
            "Suggested actions: Define quantitative and qualitative metrics for each identified AI risk. "
            "Select fairness metrics appropriate to the deployment context (demographic parity, equalized odds, individual fairness). "
            "Establish baseline performance measurements across demographic groups before deployment. "
            "Define measurement frequency for ongoing monitoring — continuous vs. periodic based on risk level. "
            "Document metric limitations and known measurement challenges. "
            "Validate measurement approaches against real-world outcomes where possible."
        ),
    },
    {
        "article_ref": "MEASURE 2 Actions",
        "section_path": ["MEASURE", "AI_Risk_Evaluation"],
        "content": (
            "NIST AI RMF MEASURE 2 — AI systems are evaluated for trustworthy characteristics. "
            "Suggested actions: Conduct pre-deployment testing against all defined performance, fairness, and safety acceptance criteria. "
            "Use red-teaming and adversarial testing to identify failure modes not captured by standard test sets. "
            "Evaluate AI system behavior on edge cases and distributional outliers. "
            "Test AI system performance on disaggregated demographic subgroups. "
            "Assess explainability of AI outputs against requirements for the deployment context. "
            "Document all evaluation results, including negative results, in the model card or system documentation."
        ),
    },
    {
        "article_ref": "MEASURE 3 Actions",
        "section_path": ["MEASURE", "Risk_Tracking"],
        "content": (
            "NIST AI RMF MEASURE 3 — AI risks and performance are tracked and measured over time. "
            "Suggested actions: Implement production monitoring dashboards tracking key performance and fairness metrics. "
            "Set alert thresholds that trigger human review when metrics degrade beyond acceptable bounds. "
            "Monitor for concept drift and distributional shift in AI inputs and outputs. "
            "Track AI system incidents and near-misses in a centralized incident registry. "
            "Conduct periodic performance audits comparing production outcomes to pre-deployment test results. "
            "Report monitoring results to AI governance stakeholders on defined cadence."
        ),
    },
    {
        "article_ref": "MEASURE 4 Actions",
        "section_path": ["MEASURE", "Feedback_Measurement"],
        "content": (
            "NIST AI RMF MEASURE 4 — Feedback about AI system performance is collected and integrated. "
            "Suggested actions: Establish user feedback channels for reporting AI system errors, unexpected behavior, and harms. "
            "Implement mechanisms for affected individuals to report discriminatory or harmful AI outcomes. "
            "Aggregate and analyze feedback to identify systematic failure patterns. "
            "Track feedback-driven improvements and communicate changes back to reporting users. "
            "Include affected community feedback in periodic AI system reviews. "
            "Use feedback data to update training sets and improve future model versions."
        ),
    },
    # MANAGE pillar
    {
        "article_ref": "MANAGE 1 Actions",
        "section_path": ["MANAGE", "Risk_Treatment_Plan"],
        "content": (
            "NIST AI RMF MANAGE 1 — AI risks based on assessments and other analytical output are addressed. "
            "Suggested actions: Develop risk treatment plans for each significant identified AI risk, specifying: treatment option (mitigate, transfer, avoid, accept); specific actions; resource requirements; timelines; and accountable owner. "
            "Document risk acceptance decisions with explicit rationale and senior leadership sign-off. "
            "Implement risk mitigations before deployment for risks above the organizational threshold. "
            "Track risk treatment plan implementation and verify effectiveness. "
            "Update risk treatment plans when new information emerges from monitoring or incidents. "
            "Communicate significant residual risks to operators and users."
        ),
    },
    {
        "article_ref": "MANAGE 2 Actions",
        "section_path": ["MANAGE", "Risk_Response"],
        "content": (
            "NIST AI RMF MANAGE 2 — Strategies to address AI risks and benefits are planned. "
            "Suggested actions: Define incident response procedures for different AI failure scenarios including: minor performance degradation, bias discovery, safety incidents, and catastrophic failures. "
            "Establish rollback procedures to revert AI systems to previous versions when issues are detected. "
            "Develop contingency plans for AI system unavailability including human fallback procedures. "
            "Train response teams on AI incident procedures through regular exercises. "
            "Establish communication templates for notifying affected parties of AI incidents. "
            "Define criteria for system suspension versus continued operation under degraded performance."
        ),
    },
    {
        "article_ref": "MANAGE 3 Actions",
        "section_path": ["MANAGE", "Residual_Risks"],
        "content": (
            "NIST AI RMF MANAGE 3 — AI risks and benefits are evaluated for AI systems and for the risk management process. "
            "Suggested actions: Evaluate whether risk treatments have achieved target risk levels post-implementation. "
            "Document residual risks that remain after treatment and communicate to stakeholders. "
            "Conduct periodic residual risk reviews to assess whether previously accepted risks remain acceptable. "
            "Track emergence of new risks from AI system interactions with its operating environment. "
            "Evaluate AI risk management process effectiveness and identify process improvements. "
            "Compare organizational AI risk profile to industry benchmarks and regulatory expectations."
        ),
    },
    {
        "article_ref": "MANAGE 4 Actions",
        "section_path": ["MANAGE", "Risk_Monitoring"],
        "content": (
            "NIST AI RMF MANAGE 4 — Risk treatment is monitored and managed on an ongoing basis. "
            "Suggested actions: Conduct regular post-deployment reviews assessing: performance against acceptance criteria, fairness metric trends, incident frequency, and user feedback. "
            "Escalate performance degradation, emerging risks, or incidents to appropriate governance levels. "
            "Maintain AI system change logs documenting all modifications to models, training data, and configurations. "
            "Plan for AI system retirement and define retirement triggers including: persistent performance failure, loss of vendor support, regulatory non-compliance, and superior replacement availability. "
            "Conduct structured retrospectives after AI system retirement to capture lessons learned for future systems. "
            "Ensure monitoring responsibilities are sustained over the full operational lifetime of AI systems."
        ),
    },
]


def _to_ltree(path: list[str]) -> str:
    parts = []
    for p in path:
        p = re.sub(r"[^a-zA-Z0-9]", "_", p)
        p = re.sub(r"_+", "_", p).strip("_")
        parts.append(p)
    return ".".join(parts)


def _corpus_hash(chunks):
    return hashlib.sha256("".join(c["content"] for c in chunks).encode()).hexdigest()


def ingest_playbook():
    print("Loading embedding model...")
    from fastembed import TextEmbedding
    model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    list(model.embed(["warmup"]))
    print("Model ready.")

    conn = psycopg2.connect(DATABASE_URL, connect_timeout=15)
    cur = conn.cursor()

    # Check if already ingested
    cur.execute("SELECT doc_id FROM regulatory_documents WHERE title LIKE '%Playbook%' AND framework = 'NIST AI RMF'")
    if cur.fetchone():
        print("NIST Playbook already ingested. Skipping.")
        cur.close(); conn.close(); return

    doc_id = str(uuid.uuid4())
    version_hash = _corpus_hash(PLAYBOOK_CHUNKS)
    cur.execute(
        "INSERT INTO regulatory_documents (doc_id, title, framework, version, source_url, corpus_version_hash, status, metadata) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (doc_id, "NIST AI RMF Playbook — Suggested Actions",
         "NIST AI RMF", "1.0",
         "https://airc.nist.gov/Docs/2",
         version_hash, "active", "{}"),
    )
    print(f"Inserted NIST Playbook doc (doc_id={doc_id})")

    print(f"Embedding and inserting {len(PLAYBOOK_CHUNKS)} playbook chunks...")
    for i, chunk in enumerate(PLAYBOOK_CHUNKS):
        chunk_id = str(uuid.uuid4())
        emb = list(list(model.embed([chunk["content"][:512]]))[0])
        emb_str = "[" + ",".join(f"{v:.8f}" for v in emb) + "]"
        cur.execute(
            "INSERT INTO regulatory_chunks (chunk_id, doc_id, content, article_ref, section_path, chunk_index, embedding, corpus_version_hash, metadata) VALUES (%s,%s,%s,%s,%s::ltree,%s,%s::vector,%s,%s)",
            (chunk_id, doc_id, chunk["content"], chunk["article_ref"],
             _to_ltree(chunk["section_path"]), i, emb_str, version_hash, "{}"),
        )
        print(f"  [{i+1:02d}/{len(PLAYBOOK_CHUNKS)}] {chunk['article_ref']}")

    conn.commit()
    cur.close(); conn.close()
    print(f"\nDone. {len(PLAYBOOK_CHUNKS)} NIST Playbook chunks ingested.")


if __name__ == "__main__":
    ingest_playbook()
