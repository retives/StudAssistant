# # from langchain_google_genai import ChatGoogleGenerativeAI
# # from rag.vector_storage import get_vectorstore
# # from langchain_ollama import OllamaEmbeddings
# # from langchain_community.vectorstores import FAISS
# #
# # embeddings = OllamaEmbeddings(model="nomic-embed-text")
# # vectorstore = FAISS.load_local("../docs/vectorstore", embeddings, allow_dangerous_deserialization=True)
# #
# # query = "Чудик"
# # docs = vectorstore.similarity_search(query, k=5)
# #
# # for i, doc in enumerate(docs):
# #     print(f"--- Chunk {i} ---")
# #     print(doc.page_content)
# #     print(f"Source: {doc.metadata.get('source')}\n")

def get_timetable(group: str):
    import re
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"https://dekanat.nung.edu.ua/cgi-bin/timetable.cgi?n=700")

        page.fill("input[id=\"group\"]", group)
        page.click("button.btn")

        page.wait_for_selector("table")

        rows = page.locator("tr").all()
        dow = page.locator("small").all()
        dow = [day.text_content() for day in dow]
        print(dow)
        timetable_data = {}
        for day_index, day in enumerate(dow):
            classes = {}
            for index, row in enumerate(rows):
                classes[str(index)] = {}
                cells = row.locator("td").all_text_contents()
                if cells:
                    classes[str(index)]["time"] = cells[1][:5]
                    classes[str(index)]["name"] = cells[2]
                if len(classes) == 8:
                    break
            rows = rows[7:]
            timetable_data[day] = classes
        browser.close()
        return timetable_data

timetable = get_timetable("ІП-22-1")

for day, classes in timetable.items():
    print(f"{day}: {classes}")