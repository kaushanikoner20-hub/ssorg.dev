"""Stage 4: Ask ssorg. Retrieval first, then an answer grounded in that evidence.

ask_question(question) does this:
1. Pick keywords from the question (locally).
2. Find the most relevant screenshots in the local SQLite library (search.py).
3. If nothing relevant is found, STOP. The AI is not called and nothing is invented.
4. Otherwise send the question plus only those few screenshots' trimmed text and
   metadata to the local Gemma model (gemma.py, through local Ollama).
5. Check the answer in Python (citations must be retrieved screenshots) and return it.

Nothing here talks to any service except your local Ollama. Question text and
screenshot text are not logged.
"""

from dataclasses import dataclass, field

from app import config, database, gemma, search

# Possible values of AskResult.status
STATUS_ANSWERED = "answered"          # a grounded answer with citations
STATUS_NO_ANSWER = "no_answer"        # evidence found, but it does not answer the question
STATUS_NO_EVIDENCE = "no_evidence"    # nothing relevant in the library; the AI was not called
STATUS_UNGROUNDED = "ungrounded"      # the AI's answer was not tied to retrieved screenshots
STATUS_AI_UNAVAILABLE = "ai_unavailable"  # Ollama or the model could not be used
STATUS_BAD_ANSWER = "bad_answer"      # the AI replied in an unusable format
STATUS_EMPTY = "empty"                # no question was typed
STATUS_ERROR = "error"                # the library could not be read

_AI_UNAVAILABLE_STATUSES = (
    gemma.STATUS_UNAVAILABLE, gemma.STATUS_TIMEOUT, gemma.STATUS_MODEL_MISSING, gemma.STATUS_ERROR,
)


@dataclass
class AskResult:
    """Everything the interface needs to show the outcome of one question."""

    question: str
    status: str
    answer: str = ""
    message: str = ""
    support: str = ""                                         # direct / partial / none
    keywords: list[str] = field(default_factory=list)
    evidence: list[search.EvidenceItem] = field(default_factory=list)  # every retrieved screenshot
    cited_ids: list[int] = field(default_factory=list)        # the ones the answer is based on
    warnings: list[str] = field(default_factory=list)

    @property
    def cited(self) -> list[search.EvidenceItem]:
        return [item for item in self.evidence if item.id in self.cited_ids]

    @property
    def others(self) -> list[search.EvidenceItem]:
        return [item for item in self.evidence if item.id not in self.cited_ids]


def ask_question(question: str, db_path=None) -> AskResult:
    """Answer a question about the saved screenshots. Never raises."""
    question = " ".join((question or "").split())[: config.ASK_MAX_QUESTION_CHARS]
    if not question:
        return AskResult(question, STATUS_EMPTY, message="Please type a question first.")

    try:
        retrieved = search.retrieve_evidence(question, db_path=db_path)
    except database.DatabaseError as error:
        return AskResult(question, STATUS_ERROR, message=str(error))

    if not retrieved.items:
        if not retrieved.keywords:
            message = "I could not find any useful words in that question. Try mentioning a specific word, name or topic."
        else:
            message = "No matching evidence was found in your saved screenshots, so there is nothing to answer from."
        return AskResult(question, STATUS_NO_EVIDENCE, message=message, keywords=retrieved.keywords)

    result = gemma.answer_question(question, retrieved.items)  # only the retrieved evidence is sent
    base = dict(question=question, keywords=retrieved.keywords, evidence=retrieved.items, support=result.support)

    if result.status == gemma.STATUS_SUCCESS:
        return AskResult(status=STATUS_ANSWERED, answer=result.answer, cited_ids=result.cited_ids,
                         warnings=result.warnings, **base)
    if result.status == gemma.STATUS_NO_ANSWER:
        return AskResult(status=STATUS_NO_ANSWER, message=result.message, **base)
    if result.status == gemma.STATUS_UNGROUNDED:
        return AskResult(status=STATUS_UNGROUNDED, message=result.message, **base)
    if result.status in _AI_UNAVAILABLE_STATUSES:
        return AskResult(status=STATUS_AI_UNAVAILABLE, message=result.message, **base)
    return AskResult(status=STATUS_BAD_ANSWER, message=result.message, **base)