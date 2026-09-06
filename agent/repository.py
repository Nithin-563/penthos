"""Repository intelligence tools for Penthos."""

from memory.project_index import ProjectIndex
from memory.search import MemorySearch
from memory.project_context import ProjectContext


class RepositoryIntelligence:
    def __init__(self, root="."):
        self.index = ProjectIndex(root)
        self.memory_search = MemorySearch("memory")
        self.context = ProjectContext(root)

    def index_repository(self):
        result = self.index.scan()

        return {
            "file_count": result["file_count"],
            "important_files": self.index.important_files(),
        }

    def changed_files(self):
        return self.index.changed_files()

    def project_context(self):
        return self.context.build()

    def search_memory(self, query):
        return self.memory_search.search(query)
