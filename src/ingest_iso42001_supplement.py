"""Add missing ISO 42001 clauses to existing Neon document.

Adds: 5.1, 6.3, 7.1, 7.3, 7.4, 8.1, 8.2, 8.7, 10.1,
      Annex A.2, A.3, A.4, A.5, A.8, A.9, A.10

Run:
    python3 -m src.ingest_iso42001_supplement
"""
from __future__ import annotations
import os, re, uuid
import psycopg2

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_wlvpsDzh78We@ep-gentle-glitter-aqzwfi7t.c-8.us-east-1.aws.neon.tech:5432/neondb?sslmode=require",
)

SUPPLEMENT_CHUNKS: list[dict] = [
    {
        "article_ref": "ISO 42001 Clause 5.1",
        "section_path": ["Clause_5", "Leadership_and_commitment"],
        "content": (
            "ISO 42001 Clause 5.1 — Leadership and commitment. "
            "Top management shall demonstrate leadership and commitment with respect to the AI management system by: "
            "taking accountability for the effectiveness of the AIMS; ensuring AI policy and objectives are established and compatible with strategic direction; "
            "ensuring integration of AIMS requirements into the organization's business processes; "
            "promoting the use of risk-based thinking and process approach; "
            "ensuring the resources needed for the AIMS are available; "
            "communicating the importance of effective AI management and conforming to AIMS requirements; "
            "ensuring the AIMS achieves its intended outcomes; "
            "directing and supporting persons to contribute to AIMS effectiveness; "
            "promoting continual improvement of responsible AI practices; "
            "and supporting other relevant management roles to demonstrate leadership in their areas of responsibility. "
            "Leadership commitment is evidenced through resource allocation, policy approval, and active participation in AI governance reviews."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 6.3",
        "section_path": ["Clause_6", "Planning_of_changes"],
        "content": (
            "ISO 42001 Clause 6.3 — Planning of changes. "
            "When the organization determines the need for changes to the AI management system, the changes shall be carried out in a planned manner. "
            "The organization shall consider: the purpose of the changes and their potential consequences; "
            "the integrity of the AI management system; the availability of resources; "
            "the allocation or reallocation of responsibilities and authorities. "
            "AI system changes — including model updates, retraining, architectural changes, and changes to training data — "
            "must be assessed for risk impact before implementation. "
            "Change management records must document the rationale, risk assessment, approval, and post-change verification for all AIMS changes."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 7.1",
        "section_path": ["Clause_7", "Resources"],
        "content": (
            "ISO 42001 Clause 7.1 — Resources. "
            "The organization shall determine and provide the resources needed for the establishment, implementation, maintenance, and continual improvement of the AI management system. "
            "Resources include: human resources with appropriate competencies in AI development, ethics, and governance; "
            "technical infrastructure for model development, testing, and deployment; "
            "computational resources for training and inference; "
            "data management infrastructure; "
            "explainability and audit tooling; "
            "and financial resources proportionate to AI risk levels. "
            "Resource adequacy must be reviewed as AI systems scale or risk levels change. "
            "Insufficient resources for safety testing, bias evaluation, or monitoring must be reported to top management."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 7.3",
        "section_path": ["Clause_7", "Awareness"],
        "content": (
            "ISO 42001 Clause 7.3 — Awareness. "
            "Persons doing work under the organization's control shall be aware of: "
            "the AI policy; their contribution to the effectiveness of the AIMS and the benefits of improved AI management performance; "
            "the implications of not conforming to AIMS requirements; "
            "and the ethical and legal obligations associated with developing and deploying AI systems. "
            "Awareness programs must cover: what constitutes responsible AI behavior; "
            "how to identify and report AI-related risks and incidents; "
            "the rights of individuals affected by AI systems; "
            "and the organization's AI governance structures and escalation paths. "
            "Awareness is distinct from competence — it applies to all workers, not just technical staff."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 7.4",
        "section_path": ["Clause_7", "Communication"],
        "content": (
            "ISO 42001 Clause 7.4 — Communication. "
            "The organization shall determine the internal and external communications relevant to the AI management system, including: "
            "on what it will communicate (AI policy, risk decisions, incident reports, performance results); "
            "when to communicate (lifecycle milestones, incident triggers, regulatory deadlines); "
            "with whom to communicate (employees, customers, regulators, affected communities, supply chain); "
            "how to communicate (channels, formats, languages accessible to recipients); "
            "and who communicates (designated AI communication owners). "
            "External communication about AI systems must be accurate, not misleading, and proportionate to the risk level. "
            "Communication plans must address both routine reporting and crisis communication for AI incidents."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 8.1",
        "section_path": ["Clause_8", "Operational_planning_and_control"],
        "content": (
            "ISO 42001 Clause 8.1 — Operational planning and control. "
            "The organization shall plan, implement, control, and review the processes needed to meet AIMS requirements "
            "and to implement the actions determined in Clause 6. "
            "Operational controls must: establish criteria for processes; implement control of processes in accordance with criteria; "
            "maintain documented information sufficient to have confidence that processes are carried out as planned; "
            "and control planned changes and review consequences of unintended changes, taking action to mitigate adverse effects. "
            "AI-specific operational controls include: version control for models and training data; "
            "release approval gates with documented sign-offs; rollback procedures for failed deployments; "
            "and separation of development, testing, and production environments."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 8.2",
        "section_path": ["Clause_8", "AI_system_requirements"],
        "content": (
            "ISO 42001 Clause 8.2 — AI system requirements. "
            "The organization shall document requirements for AI systems before design begins, covering: "
            "intended purpose and intended users; "
            "performance requirements (accuracy, latency, throughput) with measurable acceptance criteria; "
            "fairness requirements specifying which demographic groups must achieve parity and by what metric; "
            "safety requirements including failure mode analysis and acceptable failure rates; "
            "privacy requirements (data minimization, retention limits, subject rights); "
            "security requirements (adversarial robustness, access control, model confidentiality); "
            "transparency requirements (explainability level appropriate to impact); "
            "and human oversight requirements (override mechanisms, escalation triggers). "
            "Requirements must be reviewed by technical, legal, and ethics stakeholders before development begins."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 8.7",
        "section_path": ["Clause_8", "Incident_management"],
        "content": (
            "ISO 42001 Clause 8.7 — Incident management and reporting. "
            "The organization shall establish processes to detect, report, investigate, and resolve AI system incidents. "
            "An AI incident is any event where an AI system causes or contributes to harm, unexpected behavior, or violation of requirements. "
            "Incident management must include: detection mechanisms (monitoring alerts, user feedback channels, audit log anomalies); "
            "initial response procedures (containment, impact assessment, notification triggers); "
            "investigation process (root cause analysis, affected party identification, evidence preservation); "
            "remediation (model rollback, system shutdown, corrective retraining); "
            "and regulatory notification where legally required. "
            "Post-incident reviews must update risk assessments and prevent recurrence. "
            "Incident records are documented information that must be retained."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 10.1",
        "section_path": ["Clause_10", "Continual_improvement"],
        "content": (
            "ISO 42001 Clause 10.1 — Continual improvement. "
            "The organization shall continually improve the suitability, adequacy, and effectiveness of the AI management system. "
            "Continual improvement inputs include: monitoring and measurement results (9.1); "
            "internal audit findings (9.2); management review outputs (9.3); "
            "nonconformity and corrective action results (10.2); "
            "AI incident analysis; and emerging regulatory requirements and industry standards. "
            "Improvement initiatives must be prioritized by risk reduction potential, resource availability, and strategic alignment. "
            "The organization must track improvement actions to completion and evaluate their effectiveness. "
            "Continual improvement of AI systems specifically includes: re-evaluation of fairness metrics as societal understanding evolves; "
            "adoption of improved bias detection techniques; and updates to impact assessment methodology."
        ),
    },
    {
        "article_ref": "ISO 42001 Annex A.2",
        "section_path": ["Annex_A", "A2_Policies_for_AI"],
        "content": (
            "ISO 42001 Annex A.2 — Policies for AI. "
            "A.2.1 AI policy: The organization shall establish an AI policy that defines principles, values, and commitments governing AI development and use. "
            "The policy must address: intended purpose boundaries; prohibited uses; fairness and non-discrimination commitments; "
            "transparency commitments; human oversight requirements; safety standards; and environmental responsibility. "
            "A.2.2 Topic-specific policies: Organizations shall develop topic-specific policies for high-risk AI use cases, covering: "
            "AI system classification and risk thresholds; data governance for AI; third-party AI procurement standards; "
            "employee use of AI tools; and AI in customer-facing applications. "
            "All AI policies must be reviewed at least annually and after significant AI incidents or regulatory changes."
        ),
    },
    {
        "article_ref": "ISO 42001 Annex A.3",
        "section_path": ["Annex_A", "A3_Internal_organization"],
        "content": (
            "ISO 42001 Annex A.3 — Internal organization. "
            "A.3.1 AI governance roles: Organizations shall designate roles with clear accountability for AI governance: "
            "AI Ethics Board or equivalent oversight body; Chief AI Officer or equivalent senior accountable role; "
            "AI Risk Owner for each deployed AI system; and Data Governance Lead with oversight of AI training data. "
            "A.3.2 Segregation of duties: Persons who develop and train AI systems should not be the sole reviewers of AI system fairness and safety — "
            "independent review functions must exist. "
            "A.3.3 Information security for AI: AI-specific information security controls shall address model theft, adversarial attacks, "
            "training data poisoning, and unauthorized model access. "
            "A.3.4 Project management for AI: AI development projects shall include ethics and fairness review gates before deployment."
        ),
    },
    {
        "article_ref": "ISO 42001 Annex A.4",
        "section_path": ["Annex_A", "A4_Resources_for_AI_systems"],
        "content": (
            "ISO 42001 Annex A.4 — Resources for AI systems. "
            "A.4.1 AI tools: Organizations shall maintain an inventory of AI development tools, frameworks, and platforms. "
            "Tools must be evaluated for security, reliability, and alignment with responsible AI requirements before adoption. "
            "A.4.2 AI system documentation requirements: Resources must include documentation infrastructure for model cards, "
            "datasheets for datasets, system cards, and impact assessments. "
            "A.4.3 Human resources for AI: Staffing models must ensure adequate coverage of AI ethics, fairness, security, and domain expertise. "
            "Resource gaps identified through competence assessment (Clause 7.2) must be addressed within defined timelines. "
            "A.4.4 Knowledge management: Organizations shall capture and retain knowledge about AI system design decisions, "
            "training data sources, evaluation results, and deployment configurations to support auditability."
        ),
    },
    {
        "article_ref": "ISO 42001 Annex A.5",
        "section_path": ["Annex_A", "A5_Assessing_impacts"],
        "content": (
            "ISO 42001 Annex A.5 — Assessing impacts of AI systems. "
            "A.5.1 Impact assessment process: Organizations shall conduct impact assessments for AI systems before deployment, "
            "covering: individual impacts (discrimination, privacy violation, safety harm, economic harm); "
            "group impacts (systemic bias, disparate treatment of protected groups); "
            "and societal impacts (labor market effects, concentration of power, environmental impact). "
            "A.5.2 Impact assessment methodology: The methodology must be proportionate to AI system risk — "
            "higher-risk systems require more rigorous assessment with independent review. "
            "A.5.3 Reassessment triggers: Impact assessments must be updated when: AI system functionality changes significantly; "
            "new use cases or user groups are added; adverse incidents occur; or regulatory requirements change. "
            "A.5.4 Stakeholder consultation: For high-impact AI systems, organizations shall consult affected communities "
            "before deployment and incorporate feedback into risk treatment decisions."
        ),
    },
    {
        "article_ref": "ISO 42001 Annex A.8",
        "section_path": ["Annex_A", "A8_Information_for_users"],
        "content": (
            "ISO 42001 Annex A.8 — Information for users of AI systems. "
            "A.8.1 User documentation: Organizations shall provide users with documentation covering: "
            "the AI system's intended purpose and limitations; instructions for appropriate use; "
            "known failure modes and their consequences; performance characteristics across different demographic groups; "
            "how to interpret AI outputs and confidence scores; and how to report issues. "
            "A.8.2 Notification of AI interaction: Users must be informed when they are interacting with an AI system, "
            "not a human, except where technically necessary for the service. "
            "A.8.3 Explanation of AI decisions: For AI decisions with significant individual impact, "
            "organizations must provide meaningful explanations at a level understandable to the affected person, "
            "covering the main factors that influenced the decision. "
            "A.8.4 Right to contest: Where legally applicable, organizations must provide mechanisms for individuals to contest AI-driven decisions."
        ),
    },
    {
        "article_ref": "ISO 42001 Annex A.9",
        "section_path": ["Annex_A", "A9_Use_of_AI_systems"],
        "content": (
            "ISO 42001 Annex A.9 — Use of AI systems. "
            "A.9.1 Acceptable use: Organizations shall define and enforce acceptable use policies for AI systems, "
            "covering: permitted and prohibited applications; user authentication and authorization; "
            "logging of AI system interactions for audit purposes; and consequences of misuse. "
            "A.9.2 Human oversight in use: Operational procedures must define when human review of AI outputs is mandatory "
            "before action is taken, and how humans exercise override authority. "
            "A.9.3 Monitoring AI system use: Organizations shall monitor deployed AI systems for: "
            "use outside intended purpose; performance degradation in production; "
            "demographic disparities in outcomes; and user feedback indicating harm. "
            "A.9.4 Access control: Access to AI systems must be granted on a least-privilege basis; "
            "privileged access (model training, configuration changes) requires additional authorization."
        ),
    },
    {
        "article_ref": "ISO 42001 Annex A.10",
        "section_path": ["Annex_A", "A10_Third_party_relationships"],
        "content": (
            "ISO 42001 Annex A.10 — Third-party and customer relationships. "
            "A.10.1 AI supply chain risk: Organizations using third-party AI components (pre-trained models, APIs, datasets) "
            "must assess the responsible AI practices of suppliers before procurement. "
            "Supplier assessments must cover: data governance and privacy practices; bias testing results; "
            "security controls; documentation quality; and regulatory compliance posture. "
            "A.10.2 Contractual requirements: Agreements with AI suppliers must address: "
            "notification of material model changes; incident reporting obligations; audit rights; "
            "data processing terms; and liability allocation for AI-related harms. "
            "A.10.3 Customer obligations: Organizations providing AI systems to customers must define "
            "acceptable use terms, provide adequate documentation, and establish channels for customers "
            "to report AI-related incidents or concerns. "
            "A.10.4 AI system transfer: Transfer of AI systems (models, training data, documentation) to third parties "
            "must comply with applicable data protection and IP requirements."
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


def ingest_supplement():
    print("Loading embedding model...")
    from fastembed import TextEmbedding
    model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    list(model.embed(["warmup"]))
    print("Model ready.")

    conn = psycopg2.connect(DATABASE_URL, connect_timeout=15)
    cur = conn.cursor()

    # Get existing ISO 42001 doc_id
    cur.execute("SELECT doc_id, corpus_version_hash FROM regulatory_documents WHERE framework = %s", ("ISO 42001",))
    row = cur.fetchone()
    if not row:
        print("ERROR: ISO 42001 document not found. Run ingest_iso42001.py first.")
        cur.close(); conn.close(); return
    doc_id, version_hash = row
    print(f"Found ISO 42001 doc_id: {doc_id}")

    # Get current max chunk_index
    cur.execute("SELECT max(chunk_index) FROM regulatory_chunks WHERE doc_id = %s", (doc_id,))
    max_idx = cur.fetchone()[0] or 0

    # Check which article_refs already exist
    cur.execute("SELECT article_ref FROM regulatory_chunks WHERE doc_id = %s", (doc_id,))
    existing_refs = {r[0] for r in cur.fetchall()}

    print(f"Existing chunks: {len(existing_refs)}, max_index: {max_idx}")
    print(f"Adding {len(SUPPLEMENT_CHUNKS)} supplementary chunks...")

    added = 0
    for i, chunk in enumerate(SUPPLEMENT_CHUNKS):
        if chunk["article_ref"] in existing_refs:
            print(f"  SKIP (exists): {chunk['article_ref']}")
            continue
        chunk_id = str(uuid.uuid4())
        emb = list(list(model.embed([chunk["content"][:512]]))[0])
        emb_str = "[" + ",".join(f"{v:.8f}" for v in emb) + "]"
        cur.execute(
            """
            INSERT INTO regulatory_chunks
                (chunk_id, doc_id, content, article_ref, section_path, chunk_index, embedding, corpus_version_hash, metadata)
            VALUES (%s, %s, %s, %s, %s::ltree, %s, %s::vector, %s, %s)
            """,
            (chunk_id, doc_id, chunk["content"], chunk["article_ref"],
             _to_ltree(chunk["section_path"]), max_idx + i + 1,
             emb_str, version_hash, "{}"),
        )
        print(f"  [{added+1:02d}] {chunk['article_ref']}")
        added += 1

    conn.commit()
    cur.close(); conn.close()
    print(f"\nDone. {added} new ISO 42001 chunks added.")


if __name__ == "__main__":
    ingest_supplement()
