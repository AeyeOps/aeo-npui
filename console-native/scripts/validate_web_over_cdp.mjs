#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

function parseArgs(argv) {
  const options = {
    port: 9222,
    url: null,
    screenshot: null,
    waitUntil: "domcontentloaded",
    timeoutMs: 30000,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--port") options.port = Number(argv[++index]);
    else if (arg === "--url") options.url = argv[++index];
    else if (arg === "--screenshot") options.screenshot = argv[++index];
    else if (arg === "--wait-until") options.waitUntil = argv[++index];
    else if (arg === "--timeout-ms") options.timeoutMs = Number(argv[++index]);
  }

  return options;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const endpoint = `http://127.0.0.1:${options.port}`;
  let browser;

  try {
    browser = await chromium.connectOverCDP(endpoint);
    const context = browser.contexts()[0];
    if (!context) {
      throw new Error(`No browser context available over CDP at ${endpoint}`);
    }

    const page = context.pages()[0] ?? (await context.newPage());
    if (options.url) {
      await page.goto(options.url, {
        waitUntil: options.waitUntil,
        timeout: options.timeoutMs,
      });
    }

    if (options.screenshot) {
      await fs.mkdir(path.dirname(options.screenshot), { recursive: true });
      await page.screenshot({
        path: options.screenshot,
        type: "png",
        scale: "css",
      });
    }

    const result = {
      endpoint,
      title: await page.title(),
      url: page.url(),
      screenshot: options.screenshot,
      contexts: browser.contexts().length,
      pages: context.pages().length,
    };
    console.log(JSON.stringify(result, null, 2));
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
