# Accor Plus Homepage Analytics Agent

This folder contains a small reusable agent that reads an Accor Plus homepage GA4 raw data file, analyzes the performance pattern, and writes a Markdown report with observations and improvement recommendations for `www.accorplus.com`.

It can read either one raw file or a folder of weekly files.

## Input Format

The agent accepts `.xlsx`, `.xls`, or `.csv` files with these fields:

- Date
- Page Path
- Users
- Sessions
- Engaged Sessions
- Engagement Rate
- Average Engagement Time, or Avg Engagement Time (sec)
- Conversions
- Revenue (AUD), Revenue AUD, or Revenue

## Run It

```bash
python accorplus_homepage_agent.py /path/to/AccorPlus_Homepage_GA4_Sample_Raw_Data.xlsx
```

To analyze multiple weekly extracts, put the `.xlsx` or `.csv` files in one folder and pass the folder path:

```bash
python accorplus_homepage_agent.py /path/to/weekly_homepage_exports/ --output outputs/weekly_report.md
```

To choose a report location:

```bash
python accorplus_homepage_agent.py /path/to/AccorPlus_Homepage_GA4_Sample_Raw_Data.xlsx --output outputs/my_report.md
```

## What It Reports

- Overall traffic, engagement, conversion, and revenue KPIs
- First-week vs final-week movement
- Week-by-week trend table when multiple weeks are supplied
- Best and weakest days
- Weekday patterns
- Revenue and conversion relationships with sessions and engagement
- Homepage improvement ideas and a practical testing backlog

## Notes

The script uses `pandas` to read Excel files. If you run it outside this Codex workspace and your Python environment does not already have Excel support, install:

```bash
pip install pandas openpyxl
```
