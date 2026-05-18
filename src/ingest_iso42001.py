"""Ingest ISO 42001:2023 (AI Management System) into Neon regulatory_chunks.

Uses publicly available clause summaries and annex descriptions (non-paywalled content).
Embeddings: sentence-transformers/all-MiniLM-L6-v2 via fastembed (384 dims — matches production).

Run:
    python3 -m src.ingest_iso42001
"""

from __future__ import annotations

import hashlib
import os
import uuid

import psycopg2

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_wlvpsDzh78We@ep-gentle-glitter-aqzwfi7t.c-8.us-east-1.aws.neon.tech:5432/neondb?sslmode=require",
)

# ── ISO 42001 corpus ──────────────────────────────────────────────────────────

ISO_42001_CHUNKS: list[dict] = [
    # Clause 4 — Context
    {
        "article_ref": "ISO 42001 Clause 4",
        "section_path": ["Clause 4", "Context of the organization"],
        "content": (
            "ISO 42001 Clause 4 — Context of the organization. "
            "Organizations must determine external and internal issues relevant to their purpose that affect their ability to achieve intended AI management system outcomes. "
            "This includes identifying interested parties (employees, customers, regulators, affected communities), their requirements, and their relevance to the AI system lifecycle. "
            "Organizations shall define the scope of the AI management system (AIMS), including its boundaries, applicable AI systems, and interactions with other management systems. "
            "Relevant issues include legal, regulatory, competitive, and socio-cultural factors influencing AI development and deployment."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 4.1",
        "section_path": ["Clause 4", "Understanding the organization and its context"],
        "content": (
            "ISO 42001 Clause 4.1 — Understanding the organization and its context. "
            "The organization shall determine external issues (regulatory environment, technology landscape, societal expectations, market conditions) "
            "and internal issues (organizational values, culture, knowledge, governance structures) relevant to AI system development and deployment. "
            "This analysis informs risk assessment and shapes the AI management system boundaries."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 4.2",
        "section_path": ["Clause 4", "Understanding needs and expectations of interested parties"],
        "content": (
            "ISO 42001 Clause 4.2 — Needs and expectations of interested parties. "
            "Organizations must identify interested parties relevant to the AIMS: internal stakeholders (employees, developers, leadership) "
            "and external parties (customers, regulators, civil society, affected communities). "
            "Requirements from interested parties that are applicable to the AI system must be determined and documented. "
            "This includes data subjects whose data is processed, users of AI-enabled products/services, and oversight bodies."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 4.3",
        "section_path": ["Clause 4", "Determining the scope of the AI management system"],
        "content": (
            "ISO 42001 Clause 4.3 — Scope of the AI management system. "
            "The organization must define the boundaries and applicability of the AIMS. "
            "Scope determination considers external/internal issues (4.1), interested party requirements (4.2), and the organization's AI activities. "
            "The scope must be documented and specify which AI systems, functions, and organizational units are included. "
            "Exclusions from scope must be justified. The documented scope must be available to interested parties."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 4.4",
        "section_path": ["Clause 4", "AI management system"],
        "content": (
            "ISO 42001 Clause 4.4 — AI management system establishment. "
            "The organization shall establish, implement, maintain, and continually improve an AI management system "
            "in accordance with ISO 42001 requirements. "
            "The AIMS must address the full AI system lifecycle: design, development, deployment, monitoring, and decommissioning. "
            "Integration with existing management systems (ISO 9001, ISO 27001) is encouraged where applicable."
        ),
    },

    # Clause 5 — Leadership
    {
        "article_ref": "ISO 42001 Clause 5",
        "section_path": ["Clause 5", "Leadership"],
        "content": (
            "ISO 42001 Clause 5 — Leadership and commitment. "
            "Top management must demonstrate leadership and commitment to the AI management system by: "
            "ensuring the AIMS is compatible with strategic direction; providing resources; communicating importance of AI risk management; "
            "promoting a culture of responsible AI; and supporting other management roles. "
            "Leadership accountability for AI outcomes is fundamental to ISO 42001 compliance."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 5.2",
        "section_path": ["Clause 5", "AI policy"],
        "content": (
            "ISO 42001 Clause 5.2 — AI policy. "
            "Top management must establish an AI policy that: is appropriate to the organization's purpose; "
            "provides a framework for setting AI objectives; includes commitments to satisfy applicable requirements; "
            "commits to continual improvement; and addresses responsible AI principles (fairness, transparency, accountability, safety). "
            "The AI policy must be documented, communicated internally, and available to interested parties. "
            "It must align with the organization's risk appetite and ethical commitments."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 5.3",
        "section_path": ["Clause 5", "Organizational roles, responsibilities and authorities"],
        "content": (
            "ISO 42001 Clause 5.3 — Roles, responsibilities, and authorities. "
            "Top management must assign and communicate roles and responsibilities for the AIMS. "
            "Key roles include: AI governance function (oversight); AI risk owner (accountable for specific AI systems); "
            "AI system operator (day-to-day use); data governance lead; and compliance/audit function. "
            "Responsibilities must cover the full AI lifecycle including incident response and decommissioning. "
            "Cross-functional accountability between IT, legal, ethics, and business units is required."
        ),
    },

    # Clause 6 — Planning
    {
        "article_ref": "ISO 42001 Clause 6",
        "section_path": ["Clause 6", "Planning"],
        "content": (
            "ISO 42001 Clause 6 — Planning for the AI management system. "
            "Organizations must plan actions to address risks and opportunities affecting AI system integrity, fairness, safety, and compliance. "
            "Planning encompasses: AI risk assessment methodology; treatment of identified risks; setting measurable AI objectives; "
            "and planning changes to the AIMS in a controlled manner. "
            "Risk-based thinking is central — potential harms from AI systems must be systematically identified, evaluated, and treated."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 6.1",
        "section_path": ["Clause 6", "Actions to address risks and opportunities"],
        "content": (
            "ISO 42001 Clause 6.1 — Actions to address risks and opportunities. "
            "The organization shall determine risks and opportunities arising from AI system development and deployment: "
            "technical risks (model failures, data quality issues, adversarial attacks); "
            "ethical risks (bias, discrimination, lack of transparency); "
            "operational risks (availability, security, misuse); "
            "and legal/regulatory risks (non-compliance, liability). "
            "Risk assessment must consider likelihood, severity, and reversibility of harms to individuals and society. "
            "Documented risk treatment plans with assigned owners are required."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 6.1.2",
        "section_path": ["Clause 6", "AI risk assessment"],
        "content": (
            "ISO 42001 Clause 6.1.2 — AI risk assessment. "
            "Organizations must establish, implement, and maintain an AI risk assessment process that: "
            "defines risk acceptance criteria; identifies AI risks including those to data subjects and third parties; "
            "analyzes likelihood and potential consequences; evaluates risks against acceptance criteria; "
            "and documents risk assessment results. "
            "AI-specific risks include algorithmic bias, lack of explainability, data poisoning, model drift, and unintended use. "
            "Impact assessments must consider vulnerable groups and systemic societal effects."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 6.2",
        "section_path": ["Clause 6", "AI objectives and planning to achieve them"],
        "content": (
            "ISO 42001 Clause 6.2 — AI objectives and planning. "
            "The organization must establish AI objectives at relevant functions and levels. "
            "AI objectives must be: consistent with AI policy; measurable; monitored; communicated; and updated as appropriate. "
            "Objectives must address responsible AI dimensions: accuracy, fairness, robustness, privacy, security, transparency, and human oversight. "
            "Planning must specify: what will be done; required resources; responsible parties; completion timeline; and evaluation methods."
        ),
    },

    # Clause 7 — Support
    {
        "article_ref": "ISO 42001 Clause 7",
        "section_path": ["Clause 7", "Support"],
        "content": (
            "ISO 42001 Clause 7 — Support. "
            "Organizations must provide resources, competence, awareness, communication, and documented information to support the AIMS. "
            "AI-specific support requirements include: technical infrastructure for model development and monitoring; "
            "data management capabilities; explainability and audit tooling; and AI ethics competence across teams. "
            "Support mechanisms must scale with the complexity and risk level of deployed AI systems."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 7.2",
        "section_path": ["Clause 7", "Competence"],
        "content": (
            "ISO 42001 Clause 7.2 — Competence. "
            "Organizations must determine the competence necessary for AI system development, deployment, and oversight: "
            "technical competence (ML engineering, data science, software development); "
            "domain competence (understanding of application context and affected communities); "
            "ethics and fairness competence; and regulatory/legal knowledge. "
            "Evidence of competence must be documented. Where gaps exist, training, hiring, or external expertise must be obtained. "
            "Competence requirements evolve as AI capabilities and risks change."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 7.5",
        "section_path": ["Clause 7", "Documented information"],
        "content": (
            "ISO 42001 Clause 7.5 — Documented information. "
            "The AIMS must include documented information required by ISO 42001 and determined by the organization as necessary. "
            "Required documentation includes: AI policy; scope; risk assessment results; risk treatment plans; AI objectives; "
            "competence evidence; operational controls; monitoring results; internal audit results; and management review outputs. "
            "Documentation must be controlled: version-managed, access-controlled, retained appropriately, and protected from inadvertent alteration."
        ),
    },

    # Clause 8 — Operation
    {
        "article_ref": "ISO 42001 Clause 8",
        "section_path": ["Clause 8", "Operation"],
        "content": (
            "ISO 42001 Clause 8 — Operation. "
            "The organization must plan, implement, control, and review processes needed to meet AIMS requirements and implement actions from Clause 6. "
            "Operational controls cover the full AI lifecycle: data acquisition and management; model design, training, and validation; "
            "system testing and deployment; runtime monitoring; incident management; and decommissioning. "
            "Change management processes must ensure that modifications to AI systems are assessed for risk before implementation."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 8.3",
        "section_path": ["Clause 8", "AI system impact assessment"],
        "content": (
            "ISO 42001 Clause 8.3 — AI system impact assessment. "
            "Before deploying AI systems, organizations must conduct impact assessments covering: "
            "intended use and potential misuse scenarios; affected individuals and communities; "
            "fairness and non-discrimination analysis; privacy implications; safety-critical failure modes; "
            "and environmental impact. "
            "Impact assessments must be documented, reviewed by relevant stakeholders, and updated when the AI system changes significantly. "
            "High-risk deployments require more rigorous assessment with independent review."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 8.4",
        "section_path": ["Clause 8", "AI system lifecycle"],
        "content": (
            "ISO 42001 Clause 8.4 — AI system lifecycle. "
            "ISO 42001 requires controls across all lifecycle stages: "
            "Design — define intended purpose, performance requirements, fairness constraints, and data requirements; "
            "Development — implement bias testing, model validation, security controls, and documentation; "
            "Deployment — verify operational environment, user training, monitoring setup, and incident response readiness; "
            "Monitoring — track performance, detect drift, assess emerging risks, and review for continued appropriateness; "
            "Decommissioning — plan data retention/deletion, manage model artifacts, and document lessons learned."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 8.5",
        "section_path": ["Clause 8", "Data for AI systems"],
        "content": (
            "ISO 42001 Clause 8.5 — Data for AI systems. "
            "Organizations must establish controls for data used in AI systems: "
            "data quality (accuracy, completeness, representativeness, timeliness); "
            "data governance (lineage, provenance, access control, retention); "
            "bias assessment in training data; "
            "privacy and consent compliance; "
            "and handling of sensitive attributes. "
            "Training, validation, and test datasets must be managed separately with documented selection criteria. "
            "Data used for AI must align with intended use and not introduce discriminatory patterns."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 8.6",
        "section_path": ["Clause 8", "Information for users of AI systems"],
        "content": (
            "ISO 42001 Clause 8.6 — Information for users of AI systems. "
            "Organizations must provide users with adequate information about AI systems: "
            "intended purpose and limitations; performance characteristics and known failure modes; "
            "instructions for appropriate use; information about human oversight mechanisms; "
            "how to report concerns or incidents; and contact information for responsible parties. "
            "Information must be clear, accessible, and proportionate to the risk level of the AI system. "
            "Transparency obligations apply to both internal and external users."
        ),
    },

    # Clause 9 — Performance evaluation
    {
        "article_ref": "ISO 42001 Clause 9",
        "section_path": ["Clause 9", "Performance evaluation"],
        "content": (
            "ISO 42001 Clause 9 — Performance evaluation. "
            "Organizations must monitor, measure, analyze, and evaluate the AI management system and deployed AI systems. "
            "Performance evaluation covers: AI system technical performance (accuracy, robustness, fairness metrics); "
            "AIMS effectiveness; compliance with AI policy and objectives; and risk treatment adequacy. "
            "Internal audits must verify AIMS conformance. Management review must assess overall AIMS performance and drive improvement."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 9.1",
        "section_path": ["Clause 9", "Monitoring, measurement, analysis and evaluation"],
        "content": (
            "ISO 42001 Clause 9.1 — Monitoring and measurement. "
            "Organizations must determine: what needs to be monitored (AI system performance, fairness metrics, drift indicators); "
            "monitoring and measurement methods; when monitoring occurs; and when results are analyzed and reported. "
            "Continuous monitoring of production AI systems must detect performance degradation, bias emergence, and anomalous behavior. "
            "Results must be documented and trigger corrective actions when thresholds are exceeded. "
            "Monitoring must cover both technical metrics and societal impact indicators."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 9.2",
        "section_path": ["Clause 9", "Internal audit"],
        "content": (
            "ISO 42001 Clause 9.2 — Internal audit. "
            "The organization must conduct internal audits of the AIMS at planned intervals to determine whether it: "
            "conforms to ISO 42001 requirements; conforms to the organization's own AIMS requirements; and is effectively implemented and maintained. "
            "Audit program must consider importance of processes, risk levels, and previous audit results. "
            "Auditors must be objective and impartial — not audit their own work. "
            "Nonconformities and corrective actions must be documented and tracked to closure."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 9.3",
        "section_path": ["Clause 9", "Management review"],
        "content": (
            "ISO 42001 Clause 9.3 — Management review. "
            "Top management must review the AIMS at planned intervals to ensure its continuing suitability, adequacy, and effectiveness. "
            "Review inputs include: status of actions from previous reviews; changes in external/internal issues; "
            "AI system performance and incidents; audit results; nonconformities; monitoring results; interested party feedback; "
            "and opportunities for improvement. "
            "Review outputs must include decisions on improvement opportunities and AIMS changes. Results must be documented."
        ),
    },

    # Clause 10 — Improvement
    {
        "article_ref": "ISO 42001 Clause 10",
        "section_path": ["Clause 10", "Improvement"],
        "content": (
            "ISO 42001 Clause 10 — Improvement. "
            "Organizations must continually improve the suitability, adequacy, and effectiveness of the AI management system. "
            "When nonconformities occur, organizations must: react to control and correct them; evaluate causes; "
            "determine if similar nonconformities exist elsewhere; implement corrective actions; and review effectiveness. "
            "Continual improvement draws on audit results, monitoring data, incident analysis, and management review outputs. "
            "AI-specific improvements address emerging risks, technology changes, and evolving regulatory requirements."
        ),
    },
    {
        "article_ref": "ISO 42001 Clause 10.2",
        "section_path": ["Clause 10", "Nonconformity and corrective action"],
        "content": (
            "ISO 42001 Clause 10.2 — Nonconformity and corrective action. "
            "When a nonconformity occurs (including AI system incidents, fairness failures, or policy violations): "
            "take action to control and correct it; evaluate need for action to eliminate root cause; "
            "implement necessary corrective actions; review effectiveness; and update risks if necessary. "
            "For AI systems, nonconformities include: model performance below threshold; bias detected in outputs; "
            "safety incidents; data quality failures; and unauthorized use. "
            "Corrective action records must be retained as documented information."
        ),
    },

    # Annex A — Controls
    {
        "article_ref": "ISO 42001 Annex A",
        "section_path": ["Annex A", "Reference control objectives and controls"],
        "content": (
            "ISO 42001 Annex A — Reference control objectives and controls. "
            "Annex A provides a comprehensive set of AI-specific controls organized by domain: "
            "A.2 Policies for AI — organizational policies governing AI development and use; "
            "A.3 Internal organization — governance structures, roles, and accountability; "
            "A.4 Resources for AI systems — human, technical, and financial resources; "
            "A.5 Assessing impacts of AI systems — impact assessment methodology; "
            "A.6 AI system lifecycle — controls for each lifecycle stage; "
            "A.7 Data for AI systems — data governance and quality controls; "
            "A.8 Information for users — transparency and disclosure requirements; "
            "A.9 Use of AI systems — operational controls for deployment; "
            "A.10 Third-party and customer relationships — supply chain and procurement controls. "
            "Organizations select applicable controls based on risk assessment results (Statement of Applicability)."
        ),
    },
    {
        "article_ref": "ISO 42001 Annex A.6",
        "section_path": ["Annex A", "A.6 AI system lifecycle"],
        "content": (
            "ISO 42001 Annex A.6 — AI system lifecycle controls. "
            "A.6.1 AI system requirements: document intended purpose, performance targets, fairness constraints, and acceptance criteria. "
            "A.6.2 AI system design: implement privacy-by-design, explainability requirements, and bias mitigation measures. "
            "A.6.3 AI system verification and validation: test against requirements before deployment; document test results. "
            "A.6.4 AI system operation: monitor in production; detect and respond to anomalies; manage incidents. "
            "A.6.5 AI system retirement: decommission safely; manage data residuals; document decommissioning rationale. "
            "Controls apply proportionally to the risk classification of the AI system."
        ),
    },
    {
        "article_ref": "ISO 42001 Annex A.7",
        "section_path": ["Annex A", "A.7 Data for AI systems"],
        "content": (
            "ISO 42001 Annex A.7 — Data controls for AI systems. "
            "A.7.1 Data for development: training data must be representative, relevant, and assessed for bias and quality. "
            "A.7.2 Data acquisition: processes for sourcing data must ensure legal basis, consent where required, and provenance documentation. "
            "A.7.3 Data preparation: pre-processing steps must be documented; feature engineering must not introduce or amplify bias. "
            "A.7.4 Data management: data lineage, retention, access control, and deletion processes must be established. "
            "A.7.5 Data quality: systematic data quality assessment at all lifecycle stages with documented acceptance criteria."
        ),
    },

    # Annex B — Implementation guidance
    {
        "article_ref": "ISO 42001 Annex B",
        "section_path": ["Annex B", "Guidance on implementing AI controls"],
        "content": (
            "ISO 42001 Annex B — Implementation guidance for AI controls. "
            "Annex B provides practical guidance for implementing the controls in Annex A: "
            "Risk-based selection — organizations select controls commensurate with identified risks; "
            "Proportionality — control rigor scales with AI system risk classification and deployment context; "
            "Integration — AIMS controls should integrate with existing management systems (ISO 27001 for security, ISO 9001 for quality); "
            "Maturity approach — organizations may implement controls incrementally aligned with an AI governance maturity model; "
            "Documented justification — exclusions of Annex A controls must be justified in the Statement of Applicability."
        ),
    },

    # Fairness and bias
    {
        "article_ref": "ISO 42001 Fairness",
        "section_path": ["Core Concepts", "Fairness and non-discrimination"],
        "content": (
            "ISO 42001 — Fairness and non-discrimination requirements. "
            "ISO 42001 requires organizations to address fairness throughout the AI lifecycle: "
            "define fairness criteria appropriate to the application context and affected populations; "
            "assess training data for historical biases that could perpetuate discrimination; "
            "test AI system outputs for disparate impact across protected characteristics; "
            "implement bias mitigation techniques where disparities are identified; "
            "monitor deployed systems for fairness drift; and "
            "document fairness objectives, assessment methods, and results. "
            "Fairness requirements are context-dependent — what constitutes fair treatment varies by application domain and regulatory jurisdiction."
        ),
    },
    {
        "article_ref": "ISO 42001 Transparency",
        "section_path": ["Core Concepts", "Transparency and explainability"],
        "content": (
            "ISO 42001 — Transparency and explainability. "
            "ISO 42001 requires AI systems to be transparent to an appropriate degree: "
            "users must know they are interacting with an AI system; "
            "decisions with significant impact on individuals must be explainable at a level understandable to the affected person; "
            "the intended purpose, limitations, and performance characteristics must be disclosed; "
            "organizations must be transparent about data sources and processing methods; and "
            "audit trails must support post-hoc accountability. "
            "Explainability requirements are proportionate to risk — high-stakes decisions require more robust explanation mechanisms."
        ),
    },
    {
        "article_ref": "ISO 42001 Human oversight",
        "section_path": ["Core Concepts", "Human oversight and control"],
        "content": (
            "ISO 42001 — Human oversight and control requirements. "
            "ISO 42001 requires that AI systems support meaningful human oversight: "
            "human review mechanisms must be in place for high-risk or high-impact AI decisions; "
            "override capabilities must be available to human operators; "
            "AI system outputs must be presented in ways that support informed human judgment; "
            "escalation procedures must exist for edge cases and anomalies; "
            "and humans must retain ultimate accountability for AI-assisted decisions. "
            "The degree of required human oversight is proportionate to the risk and impact of the AI system. "
            "Fully automated decision-making requires additional safeguards."
        ),
    },
    {
        "article_ref": "ISO 42001 Accountability",
        "section_path": ["Core Concepts", "Accountability and governance"],
        "content": (
            "ISO 42001 — Accountability and AI governance. "
            "ISO 42001 establishes clear accountability requirements: "
            "organizations must designate accountable individuals for AI systems and the AIMS; "
            "governance structures must provide oversight of AI activities across the organization; "
            "accountability must extend to third-party AI systems used by the organization (supply chain); "
            "incident response procedures must assign clear responsibilities; "
            "and compliance with the AIMS must be auditable. "
            "AI governance aligns with board-level responsibility for organizational risk management. "
            "ISO 42001 certification demonstrates commitment to responsible AI governance to stakeholders and regulators."
        ),
    },
]


def _to_ltree(path: list[str]) -> str:
    """Convert list of path components to ltree dot-notation (alphanumeric + underscores only)."""
    import re
    parts = []
    for p in path:
        p = re.sub(r"[^a-zA-Z0-9]", "_", p)
        p = re.sub(r"_+", "_", p).strip("_")
        parts.append(p)
    return ".".join(parts)


def _get_embedding(text: str, model) -> list[float]:
    return list(list(model.embed([text[:512]]))[0])


def _corpus_version_hash(chunks: list[dict]) -> str:
    content = "".join(c["content"] for c in chunks)
    return hashlib.sha256(content.encode()).hexdigest()


def ingest_iso42001():
    print("Loading embedding model (all-MiniLM-L6-v2)...")
    from fastembed import TextEmbedding
    model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    list(model.embed(["warmup"]))
    print("Model ready.")

    conn = psycopg2.connect(DATABASE_URL, connect_timeout=15)
    cur = conn.cursor()

    # Check if already ingested
    cur.execute("SELECT doc_id FROM regulatory_documents WHERE framework = %s", ("ISO 42001",))
    existing = cur.fetchone()
    if existing:
        print(f"ISO 42001 already ingested (doc_id={existing[0]}). Delete first to re-ingest.")
        cur.close()
        conn.close()
        return

    # Insert document record
    doc_id = str(uuid.uuid4())
    version_hash = _corpus_version_hash(ISO_42001_CHUNKS)
    cur.execute(
        """
        INSERT INTO regulatory_documents (doc_id, title, framework, version, source_url, corpus_version_hash, status, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            doc_id,
            "ISO/IEC 42001:2023 Artificial Intelligence Management System",
            "ISO 42001",
            "2023",
            "https://www.iso.org/standard/81230.html",
            version_hash,
            "active",
            "{}",
        ),
    )
    print(f"Inserted regulatory_documents row (doc_id={doc_id})")

    # Insert chunks
    print(f"Embedding and inserting {len(ISO_42001_CHUNKS)} chunks...")
    for i, chunk in enumerate(ISO_42001_CHUNKS):
        chunk_id = str(uuid.uuid4())
        emb = _get_embedding(chunk["content"], model)
        emb_str = "[" + ",".join(f"{v:.8f}" for v in emb) + "]"
        cur.execute(
            """
            INSERT INTO regulatory_chunks
                (chunk_id, doc_id, content, article_ref, section_path, chunk_index, embedding, corpus_version_hash, metadata)
            VALUES (%s, %s, %s, %s, %s::ltree, %s, %s::vector, %s, %s)
            """,
            (
                chunk_id,
                doc_id,
                chunk["content"],
                chunk["article_ref"],
                _to_ltree(chunk["section_path"]),
                i,
                emb_str,
                version_hash,
                "{}",
            ),
        )
        print(f"  [{i+1:02d}/{len(ISO_42001_CHUNKS)}] {chunk['article_ref']}")

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nDone. {len(ISO_42001_CHUNKS)} ISO 42001 chunks ingested.")


if __name__ == "__main__":
    ingest_iso42001()
