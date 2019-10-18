import argparse
import asyncio
import os
import sqlite3
import csv
import time
import urllib.request
import urllib.error
from pyppeteer import launch
from pyppeteer import errors
import logging


def screenshot_csv(csv_in_name, csv_out_name, pics_out_path, screenshot_method, timeout_duration, async_num):
    """Fetches urls from the input CSV and takes a screenshot

    Parameters
    ----------
    csv_in_name : str
        The CSV file with the current urls.
    csv_out_name : str
        The CSV file to write the index.
    pics_out_path : str
        Directory to output the screenshots.
    screenshot_method : int
        Which method to take the screenshots, 0 for chrome, 1 for puppeteer, 2 for cutycapt.
    timeout_duration : str
        Duration before timeout when going to each website.

    """

    # async = 3: time = 16
    # async = 1: time = 38 min

    with open(csv_in_name, 'r') as csv_file_in:
        csv_reader = csv.reader(csv_file_in)
        next(csv_reader)  # skip header
        with open(csv_out_name, 'w+') as csv_file_out:
            csv_writer = csv.writer(csv_file_out, delimiter=',', quoting=csv.QUOTE_ALL)
            csv_writer.writerow(["archive_id", "url_id", "url", "site_status", "site_message", "screenshot_message"])

            multiple_url_details = []
            while True:
                try:
                    line = next(csv_reader)  # if last line then will be caught by except

                    archive_id = line[0]
                    url_id = line[1]
                    url = line[2]

                    if len(multiple_url_details) < async_num:
                        multiple_url_details.append([archive_id, url_id, url])
                        if len(multiple_url_details) < async_num:
                            continue

                    url_status_dict = \
                        take_screenshot(multiple_url_details, pics_out_path, screenshot_method, timeout_duration)
                    for url_detail in multiple_url_details:
                        url_id = url_detail[1]
                        return_messages = url_status_dict[url_id]
                        csv_writer.writerow([url_detail[0], url_id, url_detail[2],
                                             return_messages[0], return_messages[1], return_messages[2]])

                    multiple_url_details = []

                except StopIteration:
                    # deal with the remaining urls
                    if len(multiple_url_details) != 0:
                        url_status_dict = \
                            take_screenshot(multiple_url_details, pics_out_path, screenshot_method, timeout_duration)
                        for url_detail in multiple_url_details:
                            url_id = url_detail[1]
                            return_messages = url_status_dict[url_id]
                            csv_writer.writerow([url_detail[0], url_id, url_detail[2],
                                                 return_messages[0], return_messages[1], return_messages[2]])

                    break


def screenshot_db(csv_out_name, make_csv, pics_out_path, screenshot_method, timeout_duration):
    """Fetches urls from the input DB and takes a screenshot

    Parameters
    ----------
    csv_out_name : str
        The CSV file to write the index.
    make_csv : bool
        Whether or not to output a CSV when use_db is True.
    pics_out_path : str
        Directory to output the screenshots.
    screenshot_method : int
        Which method to take the screenshots, 0 for chrome, 1 for puppeteer, 2 for cutycapt.
    timeout_duration : str
        Duration before timeout when going to each website.

    """

    print("db not fully implemented")
    return

    cursor.execute("create table if not exists current_index (archiveID int, urlID int, succeed int, "
                   "foreign key(archiveID) references collection_name(archiveID));")
    cursor.execute("delete from current_index;")
    cursor.execute("select * from current_url;")
    connection.commit()
    results = cursor.fetchall()

    if make_csv:
        csv_file_out = open(csv_out_name, "w+")
        csv_writer = csv.writer(csv_file_out, delimiter=',', quoting=csv.QUOTE_ALL)
        csv_writer.writerow(["archive_id", "url_id", "succeed_code", "current_url"])

    count = 0
    for row in results:
        count += 1
        archive_id = row[0]
        url_id = row[1]
        url = row[2]

        print("\nurl #{0} {1}".format(url_id, url))
        logging.info("url #{0} {1}".format(url_id, url))

        succeed = take_screenshot(str(archive_id), str(url_id), url, pics_out_path, screenshot_method, timeout_duration)

        cursor.execute("insert into current_index values ({0}, {1}, {2});".format(archive_id, url_id, succeed))
        if make_csv:
            csv_writer.writerow([archive_id, url_id, succeed, url])

        connection.commit()
    connection.close()
    if make_csv:
        csv_file_out.close()


def take_screenshot(multiple_url_details, pics_out_path, screenshot_method, timeout_duration):
    """Calls the function or command to take a screenshot

    Parameters
    ----------
    archive_id : str
        The archive ID.
    url_id : str
        The url ID.
    url : str
        The url to take a screenshot of.
    pics_out_path : str
        Directory to output the screenshots.
    timeout_duration : str
        Duration before timeout when going to each website.
    screenshot_method : int
        Which method to take the screenshots, 0 for chrome, 1 for puppeteer, 2 for cutycapt.

    Returns
    -------
    str(succeed) : str
        A code indicating whether how successful the screenshot was

    Reference
    ---------
    https://stackoverflow.com/questions/30361824/asynchronous-exception-handling-in-python

    """

    url_status_dict = {}                # maps each url_id to the site messages
    multiple_url_details_temp = multiple_url_details[:]  # the list to be passed into puppeteer_screenshot

    if screenshot_method == 1:
        for id_list in multiple_url_details:
            url_id = id_list[1]
            url = id_list[2]

            print("\nurl #{0} {1}".format(url_id, url))
            logging.info("url #{0} {1}".format(url_id, url))

            site_status, site_message = check_site_availability(url)
            if site_status == "FAIL":           # if the url cannot be reached
                url_status_dict[url_id] = [site_status, site_message, "Screenshot unsuccessful"]
                multiple_url_details_temp.remove(id_list)       # remove cuz this url does not need screenshot taken
                logging.info(site_status + site_message)
                print("Screenshot unsuccessful")
            else:    # list does not include successfulness cuz it will be determined by puppeteer_screenshot
                url_status_dict[url_id] = [site_status, site_message]

        if len(multiple_url_details_temp) == 0:     # if none of the urls can be reached
            return url_status_dict     # then dont need to bother trying to take screenshots

        loop = asyncio.get_event_loop()
        task = asyncio.gather(*(puppeteer_screenshot(details, pics_out_path, timeout_duration)
                                for details in multiple_url_details_temp), loop=None, return_exceptions=True)
        result = loop.run_until_complete(task)

        for return_message in result:           # map the results to its respective url_id
            url_id = return_message[0]
            returned_error = return_message[1]
            if type(errors.TimeoutError) == type(returned_error):
                url_status_dict[url_id].append("Screenshot unsuccessful")
                logging.info(str(returned_error))
                print("Screenshot unsuccessful")
            elif type(errors.NetworkError) == type(returned_error):
                url_status_dict[url_id].append("Screenshot unsuccessful")
                logging.info(str(returned_error))
                print("Screenshot unsuccessful")
            elif type(errors.PageError) == type(returned_error):
                url_status_dict[url_id].append("Screenshot unsuccessful")
                logging.info(str(returned_error))
                print("Screenshot unsuccessful")
            elif type(Exception) == type(returned_error):
                url_status_dict[url_id].append("Screenshot unsuccessful")
                logging.info(str(returned_error))
                print("Screenshot unsuccessful")
            else:
                url_status_dict[url_id].append("Screenshot successful")
                logging.info("Screenshot successful")
                print("Screenshot successful")

    return url_status_dict

    # todo cutycapt and google-chrome


        # if screenshot_method == 0:
        #     chrome_screenshot(pics_out_path, archive_id, url_id, url, timeout_duration)
        # elif screenshot_method == 2:
        #     cutycapt_screenshot(pics_out_path, archive_id, url_id, url, timeout_duration)

    # return site_status_list, site_message_list, screenshot_message_list


def chrome_screenshot(pics_out_path, archive_id, url_id, url, timeout_duration):
    command = "timeout {4}s google-chrome --headless --hide-scrollbars --disable-gpu --noerrdialogs " \
              "--enable-fast-unload --screenshot={0}{1}.{2}.png --window-size=1024x768 '{3}'" \
        .format(pics_out_path, archive_id, url_id, url, timeout_duration)
    try:
        if os.system(command) == 0:
            logging.info("Screenshot successful")
            print("Screenshot successful")
            return "Screenshot successful"
        else:
            logging.info("Screenshot unsuccessful")
            print("Screenshot unsuccessful")
            return "Screenshot unsuccessful"
    except:  # unknown error
        logging.info("Screenshot unsuccessful")
        print("Screenshot unsuccessful")
        return "Screenshot unsuccessful"


def cutycapt_screenshot(pics_out_path, archive_id, url_id, url, timeout_duration):
    command = "timeout {4}s xvfb-run --server-args=\"-screen 0, 1024x768x24\" cutycapt --url='{0}' " \
              "--out={1}{2}.{3}.png --delay=2000".format(url, pics_out_path, archive_id, url_id, timeout_duration)
    try:
        time.sleep(1)  # cutycapt needs to rest
        if os.system(command) == 0:
            logging.info("Screenshot successful")
            print("Screenshot successful")
            return "Screenshot successful"
        else:
            logging.info("Screenshot unsuccessful")
            print("Screenshot unsuccessful")
            return "Screenshot unsuccessful"
    except:  # unknown error
        logging.info("Screenshot unsuccessful")
        print("Screenshot unsuccessful")
        return "Screenshot unsuccessful"


async def puppeteer_screenshot(url_details, pics_out_path, timeout_duration):
    """Take screenshot using the pyppeteer package.

    Parameters
    ----------
    archive_id : str
        The archive ID.
    url_id : str
        The url ID.
    url : str
        The url to take a screenshot of.
    pics_out_path : str
        Directory to output the screenshots.
    timeout_duration : str
        Duration before timeout when going to each website.

    References
    ----------
    .. [1] https://pypi.org/project/pyppeteer/

    .. [2] https://github.com/ukwa/webrender-puppeteer/blob/6fcc719d64dc19a4929c02d3a445a8283bee5195/renderer.js

    """
    archive_id, url_id, url = url_details[0], url_details[1], url_details[2],

    browser = await launch(headless=True, dumpio=True)
    page = await browser.newPage()
    try:
        await page.setViewport({'height': 768, 'width': 1024})
        await page.goto(url, timeout=(int(timeout_duration) * 1000))
        await page.waitFor(1000)
        await page.reload(timeout=(int(timeout_duration) * 1000))    # reloading a site can get rid of certain popups

        await click_button(page, "I Accept")        # click through popups and banners, there could be a lot more
        await click_button(page, "I Understand")
        await click_button(page, "I Agree")
        await click_button(page, "Accept Recommended Settings")
        await click_button(page, "Close")
        await click_button(page, "Close and Accept")
        await click_button(page, "OK")
        await click_button(page, "OK, I Understand.")
        await click_button(page, "Accept")
        await click_button(page, "Accept Cookies")
        await click_button(page, "No Thanks")
        await page.keyboard.press("Escape")

        await page.screenshot(path='{0}{1}.{2}.png'.format(pics_out_path, archive_id, url_id))

    except Exception as e:
        # https://github.com/GoogleChrome/puppeteer/issues/2269
        try:
            await page.close()
            await browser.close()
        except:
            await browser.close()
        # raise e
        return url_id, e

    try:
        await page.close()
        await browser.close()
    except:
        await browser.close()
    return url_id, None


async def click_button(page, button_text):
    """Execute js script on page to click button

    Parameters
    ----------
    page : pyppeteer.page.Page
        The page to go through
    button_text: str
        Name of the button to click

    References
    ----------
    .. [1] https://github.com/ukwa/webrender-puppeteer/blob/6fcc719d64dc19a4929c02d3a445a8283bee5195/renderer.js

    Notes
    -----
    Right now only clicks popups and banners that are buttons, but some sites have banners with using a or wb_divs


    """
    await page.evaluate('''query => {
      const elements = [...document.querySelectorAll('button')];
      const targetElement = elements.find(e => e.innerText.toLowerCase().includes(query));
      targetElement && targetElement.click();
      }''', button_text.lower())


def check_site_availability(url):
    """Run a request to see if the given url is available.

    Parameters
    ----------
    url : str
        The url to check.

    Returns
    -------
    200 if the site is up and running
    302 if it was a redirect
    -7  for URL errors
    ?   for HTTP errors
    -8  for other error

    References
    ----------
    .. [1] https://stackoverflow.com/questions/1726402/in-python-how-do-i-use-urllib-to-see-if-a-website-is-404-or-200

    """
    try:
        conn = urllib.request.urlopen(url)
    except urllib.error.HTTPError as e:
        # Return code error (e.g. 404, 501, ...)
        error_message = 'HTTPError: {}'.format(e.code)
        print(error_message)
        logging.info(error_message)
        return "FAIL", error_message
    except urllib.error.URLError as e:
        # Not an HTTP-specific error (e.g. connection refused)
        error_message = 'URLError: {}'.format(e.reason)
        print(error_message)
        logging.info(error_message)
        return "FAIL", error_message
    except Exception as e:
        # other reasons such as "your connection is not secure"
        print(e)
        logging.info(e)
        return "FAIL", e

    # check if redirected
    if conn.geturl() != url:
        print("Redirected to {}".format(conn.geturl()))
        logging.info("Redirected to {}".format(conn.geturl()))
        return "LIVE", "Redirected to {}".format(conn.geturl())

    # reaching this point means it received code 200
    print("Return code 200")
    logging.info("Return code 200")
    return "LIVE", "Return code 200"


def parse_args():
    """Parses the arguments passed in from the command line.

    Returns
    ----------
    csv_in_name : str
        The CSV file with the current urls.
    csv_out_name : str
        The CSV file to write the index.
    pics_out_path : str
        Directory to output the screenshots.
    screenshot_method : int
        Which method to take the screenshots, 0 for chrome, 1 for puppeteer, 2 for cutycapt.
    use_db : bool
        Whether or not the input is a DB.
    use_csv : bool
        Whether or not the input is a CSV.
    make_csv : bool
        Whether or not to output a CSV when use_db is True.
    timeout_duration : str
        Duration before timeout when going to each website.

    """

    parser = argparse.ArgumentParser()

    parser.add_argument("--csv", type=str, help="Input CSV file with current urls")
    parser.add_argument("--db", type=str, help="Input DB file with urls")
    parser.add_argument("--picsout", type=str, help="Directory to output the screenshots")
    parser.add_argument("--indexcsv", type=str, help="The CSV file to write the index")
    parser.add_argument("--method", type=int, help="Which method to take the screenshots, "
                                                   "0 for chrome, 1 for puppeteer, 2 for cutycapt")
    parser.add_argument("--timeout", type=str, help="(optional) Specify duration before timeout for each site, "
                                                    "in seconds, default 30 seconds")
    parser.add_argument("--async", type=int, help="(optional) Specify the number of coroutines, "
                                                  "default 1 coroutine, ")

    args = parser.parse_args()

    # some command line argument error checking
    if args.csv is not None and args.indexcsv is None:
        print("invalid output index file\n")
        exit()
    if args.csv is None and args.db is None:
        print("Must provide input file\n")
        exit()
    if args.csv is not None and args.db is not None:
        print("must only use only one type of input file\n")
        exit()
    if args.picsout is None:
        print("Must specify output path for pictures\n")
        exit()
    if args.method is None:
        print("Must specify screenshot method\n")
        exit()

    pics_out_path = args.picsout + '/'
    screenshot_method = int(args.method)
    if args.async is None:
        async_num = 1
    else:
        async_num = args.async

    if args.csv is not None:
        csv_in_name = args.csv
        use_csv = True
    else:
        use_csv = False

    if args.db is not None:
        connect_sql(args.db)
        use_db = True
    else:
        use_db = False

    if args.indexcsv is not None:
        csv_out_name = args.indexcsv
        make_csv = True
    else:
        make_csv = False

    if args.timeout is None:
        timeout_duration = "30"
    else:
        timeout_duration = args.timeout

    return csv_in_name, csv_out_name, pics_out_path, screenshot_method, \
           use_db, use_csv, make_csv, timeout_duration, async_num


def connect_sql(path):
    """Connects the DB file. """

    global connection, cursor

    connection = sqlite3.connect(path)
    cursor = connection.cursor()
    connection.commit()


def set_up_logging(pics_out_path):
    """Setting up logging format.

    Parameters
    ----------
    pics_out_path : str
        Directory to output the screenshots.

    Notes
    -----
    logging parameters:
        filename: the file to output the logs
        filemode: a as in append
        format:   format of the message
        datefmt:  format of the date in the message, month-day-year hour:minute:second AM/PM
        level:    minimum message level accepted

    """

    logging.basicConfig(filename=(pics_out_path + "current_screenshot_log.txt"), filemode='a',
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        datefmt='%d-%b-%y %H:%M:%S %p', level=logging.INFO)


def main():
    csv_in_name, csv_out_name, pics_out_path, screenshot_method, use_db, use_csv, make_csv, timeout_duration, async_num\
        = parse_args()
    set_up_logging(pics_out_path)

    print("Taking screenshots")
    if use_csv:
        screenshot_csv(csv_in_name, csv_out_name, pics_out_path, screenshot_method, timeout_duration, async_num)
    if use_db:
        screenshot_db(csv_out_name, make_csv, pics_out_path, screenshot_method, timeout_duration)


main()
