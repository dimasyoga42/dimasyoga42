"""Generate a breakdown of programming languages used across a GitHub user's repositories.

Uses the GitHub GraphQL API to fetch the language byte-size breakdown for every
repository the user owns, then aggregates and prints the overall percentage per language.

Requires the same environment variables as today.py:
    ACCESS_TOKEN - a GitHub personal access token
    USER_NAME    - the GitHub username to analyze
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"


def require_env(name):
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def graphql_request(query, variables, headers):
    response = requests.post(
        GITHUB_GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers=headers,
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Request failed with status {response.status_code}: {response.text}"
        )
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


def fetch_language_bytes(username, headers, owner_affiliations=None):
    """Return a dict of {language_name: total_bytes} across all repos owned by the user."""
    if owner_affiliations is None:
        owner_affiliations = ["OWNER"]

    query = """
    query ($login: String!, $owner_affiliation: [RepositoryAffiliation], $cursor: String) {
        user(login: $login) {
            repositories(
                first: 100
                after: $cursor
                ownerAffiliations: $owner_affiliation
                isFork: false
            ) {
                edges {
                    node {
                        name
                        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
                            edges {
                                size
                                node {
                                    name
                                    color
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }"""

    language_totals = {}
    language_colors = {}
    cursor = None

    while True:
        variables = {
            "login": username,
            "owner_affiliation": owner_affiliations,
            "cursor": cursor,
        }
        data = graphql_request(query, variables, headers)
        repositories = data["user"]["repositories"]

        for edge in repositories["edges"]:
            for lang_edge in edge["node"]["languages"]["edges"]:
                lang_name = lang_edge["node"]["name"]
                lang_size = lang_edge["size"]
                language_totals[lang_name] = language_totals.get(lang_name, 0) + lang_size
                language_colors[lang_name] = lang_edge["node"]["color"]

        if not repositories["pageInfo"]["hasNextPage"]:
            break
        cursor = repositories["pageInfo"]["endCursor"]

    return language_totals, language_colors


def format_language_report(language_totals, top_n=10):
    """Turn a {language: bytes} dict into a sorted list of (language, percentage, bytes)."""
    total_bytes = sum(language_totals.values())
    if total_bytes == 0:
        return []

    sorted_languages = sorted(
        language_totals.items(), key=lambda item: item[1], reverse=True
    )

    report = []
    for language, size in sorted_languages[:top_n]:
        percentage = (size / total_bytes) * 100
        report.append((language, percentage, size))
    return report


def print_report(report):
    print(f"{'Language':<20}{'Percentage':>12}{'Bytes':>15}")
    print("-" * 47)
    for language, percentage, size in report:
        print(f"{language:<20}{percentage:>11.2f}%{size:>15,}")


BAR_WIDTH = 25
BAR_FILLED_CHAR = "█"
BAR_EMPTY_CHAR = "░"


def build_markdown_block(report, language_colors=None, bar_width=BAR_WIDTH):
    """Build a monospace ASCII bar-chart block, similar to WakaTime-style cards.

    Example line:
        C                  █████████████████░░░░░░░  17.92 %
    """
    if not report:
        return ""

    name_width = max(len(language) for language, _, _ in report) + 2
    max_percentage = max(percentage for _, percentage, _ in report)

    lines = ["```text"]
    for language, percentage, _ in report:
        filled = round(bar_width * percentage / max_percentage)
        filled = min(filled, bar_width)
        bar = (BAR_FILLED_CHAR * filled) + (BAR_EMPTY_CHAR * (bar_width - filled))
        lines.append(f"{language:<{name_width}}{bar}  {percentage:5.2f} %")
    lines.append("```")

    return "\n".join(lines)


def update_readme(markdown_block, readme_path="README.md"):
    """Replace the content between the START/END markers inside README.md."""
    start_marker = "<!--START_LANGUAGE_STATS-->"
    end_marker = "<!--END_LANGUAGE_STATS-->"

    with open(readme_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    if start_marker not in content or end_marker not in content:
        raise RuntimeError(
            f"Could not find {start_marker} / {end_marker} markers in {readme_path}. "
            "Add them to your README.md where you want the language stats to appear."
        )

    before = content.split(start_marker)[0]
    after = content.split(end_marker)[1]

    new_content = f"{before}{start_marker}\n{markdown_block}\n{end_marker}{after}"

    with open(readme_path, "w", encoding="utf-8") as handle:
        handle.write(new_content)


def main():
    access_token = require_env("ACCESS_TOKEN")
    username = require_env("USER_NAME")
    headers = {"authorization": f"token {access_token}"}

    print(f"Fetching language stats for {username}...\n")
    language_totals, language_colors = fetch_language_bytes(username, headers)
    report = format_language_report(language_totals, top_n=10)

    if not report:
        print("No language data found. Repos might be empty or all forks.")
        return

    print_report(report)

    markdown_block = build_markdown_block(report, language_colors)
    update_readme(markdown_block)
    print("\nREADME.md updated with language stats.")


if __name__ == "__main__":
    main()
