import argparse
import os
import sqlite3
import time
import csv
import asyncio
import urllib.request
import urllib.error
from pyppeteer import launch
from pyppeteer import errors
import logging

'''
todo
add flag for pyppeteer's dumpio=, so that the output doesnt have so much garbage
grouping the individual calls of click_button may increase performance
log better
more columns for why screenshot failed, timeout/page error/network error
add "screenshot unsuccessful for id:" + url_id
'''


def screenshot_csv(csv_in_name, csv_out_name, pics_out_path, screenshot_method, timeout_duration, lazy, be_lazy,
                   banner, async_num):
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
    lazy : int
        The max number of archive captures to take a screenshot of before moving on.
    be_lazy : bool
        Whether or not to take a maximum of screenshots per archive capture.
    banner : bool
        Whether or not to remove the Archive-It banner

    """

    with open(csv_in_name, 'r') as csv_file_in:
        csv_reader = csv.reader(csv_file_in)
        next(csv_reader)  # skip header
        with open(csv_out_name, 'w+') as csv_file_out:
            csv_writer = csv.writer(csv_file_out, delimiter=',', quoting=csv.QUOTE_ALL)
            csv_writer.writerow(
                ["archive_id", "url_id", "date", "url", "site_status", "site_message", "screenshot_message"])

            compare = '0'
            multiple_url_details = []
            while True:
                try:
                    line = next(csv_reader)  # if last line then will be caught by except

                    archive_id = str(line[0])
                    url_id = line[1]
                    date = line[2]
                    url = line[3]

                    if url == "":
                        continue

                    if be_lazy is True:  # makes running faster by not doing hundreds of archive sites
                        if url_id != compare:
                            count = 0
                            compare = url_id
                        else:
                            count += 1
                            if count > lazy:
                                continue

                    if len(multiple_url_details) < async_num:
                        multiple_url_details.append([archive_id, url_id, date, url])
                        if len(multiple_url_details) < async_num:
                            continue

                    url_status_dict = \
                        take_screenshot(multiple_url_details, pics_out_path, screenshot_method, timeout_duration, banner)
                    for url_detail in multiple_url_details:
                        url_id = url_detail[1]
                        return_messages = url_status_dict[url_id]
                        csv_writer.writerow([url_detail[0], url_id, url_detail[2], url_detail[3],
                                             return_messages[0], return_messages[1], return_messages[2]])

                    multiple_url_details = []

                except StopIteration:
                    if len(multiple_url_details) != 0:
                        url_status_dict = \
                            take_screenshot(multiple_url_details, pics_out_path, screenshot_method, timeout_duration, banner)
                        for i in range(len(multiple_url_details)):
                            url_id = url_detail[1]
                            return_messages = url_status_dict[url_id]
                            csv_writer.writerow([url_detail[0], url_id, url_detail[2], url_detail[3],
                                                 return_messages[0], return_messages[1], return_messages[2]])
                    break

def screenshot_db(csv_out_name, pics_out_path, screenshot_method, make_csv, timeout_duration, lazy, be_lazy, banner):
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
    lazy : int
        The max number of archive captures to take a screenshot of before moving on.
    be_lazy : bool
        Whether or not to take a maximum of screenshots per archive capture.
    banner : bool
        Whether or not to remove the Archive-It banner

   """

    print("db not fully implemented")
    return

    cursor.execute("create table if not exists archive_index (archiveID int, urlID int, date text, succeed int, "
                   "foreign key(archiveID) references collection_name(archiveID));")
    cursor.execute("delete from archive_index;")
    cursor.execute("select * from archive_urls where url is not null;")
    connection.commit()
    results = cursor.fetchall()

    if make_csv:
        csv_file_out = open(csv_out_name, "w+")
        csv_writer = csv.writer(csv_file_out, delimiter=',', quoting=csv.QUOTE_ALL)
        csv_writer.writerow(["archive_id", "url_id", "date", "succeed_code", "archive_url"])

    count = 0
    compare = '0'
    for row in results:
        url_id = row[1]

        if be_lazy is True:  # makes running faster by not doing hundreds of archive site
            if url_id != compare:
                count = 0
                compare = url_id
            else:
                count += 1
                if count > lazy:
                    continue

        archive_id = row[0]
        date = row[2]
        url = row[3]

        print("\nurl #{0} {1}".format(url_id, url))
        logging.info("url #{0} {1}".format(url_id, url))

        succeed = take_screenshot(archive_id, url_id, date, url, pics_out_path, screenshot_method,
                                  timeout_duration, banner)

        cursor.execute("insert into archive_index values ({0}, {1}, '{2}', {3});"
                       .format(archive_id, url_id, date, succeed))
        if make_csv:
            csv_writer.writerow([archive_id, url_id, date, succeed, url])

        connection.commit()

    connection.close()

    if make_csv:
        csv_file_out.close()


def take_screenshot(multiple_url_details, pics_out_path, screenshot_method, timeout_duration, banner):
    """Calls the function or command to take a screenshot

    Parameters
    ----------
    archive_id : str
        The archive ID.
    url_id : str
        The url ID.
    date : str
        The date of the archive capture.
    url : str
        The url to take a screenshot of.
    pics_out_path : str
        Directory to output the screenshots.
    timeout_duration : str
        Duration before timeout when going to each website.
    screenshot_method : int
        Which method to take the screenshots, 0 for chrome, 1 for puppeteer, 2 for cutycapt.
    banner : bool
        Whether or not to remove the Archive-It banner

    Returns
    -------
    str(succeed) : str
        A code indicating whether how successful the screenshot was

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
                logging.info(site_message)
                print("Screenshot unsuccessful")
            else:    # list does not include successfulness cuz it will be determined by puppeteer_screenshot
                url_status_dict[url_id] = [site_status, site_message]

        if len(multiple_url_details_temp) == 0:     # if none of the urls can be reached
            return url_status_dict     # then dont need to bother trying to take screenshots

        loop = asyncio.get_event_loop()
        task = asyncio.gather(*(puppeteer_screenshot(details, pics_out_path, timeout_duration, banner)
                                for details in multiple_url_details), loop=None, return_exceptions=True)
        result = loop.run_until_complete(task)

        for return_message in result:  # map the results to its respective url_id
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

    # todo
    # if screenshot_method == 0:
    #     return site_status, site_message, chrome_screenshot(pics_out_path, archive_id, url_id, date, url, timeout_duration)
    # elif screenshot_method == 2:
    #     return site_status, site_message, cutycapt_screenshot(pics_out_path, archive_id, url_id, date, url, timeout_duration)
    return url_status_dict


async def puppeteer_screenshot(url_details, pics_out_path, timeout_duration, banner):
    """Take screenshot using the pyppeteer package.

    Parameters
    ----------
    archive_id : str
        The archive ID.
    url_id : str
        The url ID.
    date : str
        The date of the archive capture.
    url : str
        The url to take a screenshot of.
    pics_out_path : str
        Directory to output the screenshots.
    timeout_duration : str
        Duration before timeout when going to each website.
    banner : bool
        Whether or not to remove the Archive-It banner

    References
    ----------
    .. [1] https://pypi.org/project/pyppeteer/

    """
    archive_id, url_id, date, url = url_details[0], url_details[1], url_details[2], url_details[3],

    try:
        browser = await launch(headless=True, dumpio=True)
        page = await browser.newPage()

        await page.setViewport({'height': 768, 'width': 1024})
        await page.goto(url, timeout=(int(timeout_duration) * 1000))

        if not banner:
            await remove_banner(page)        # edit css of page to remove archive-it banner

        await page.screenshot(path='{0}{1}.{2}.{3}.png'.format(pics_out_path, archive_id, url_id, date))

    except Exception as e:
        # https://github.com/GoogleChrome/puppeteer/issues/2269
        try:
            await page.close()
            await browser.close()
        except:
            await browser.close()
        raise e

    try:
        await page.close()
        await browser.close()
    except:
        await browser.close()


def chrome_screenshot(pics_out_path, archive_id, url_id, date, url, timeout_duration):
    command = "timeout {5}s google-chrome --headless --hide-scrollbars --disable-gpu --noerrdialogs " \
              "--enable-fast-unload --screenshot={0}{1}.{2}.{3}.png --window-size=1024x768 '{4}'" \
        .format(pics_out_path, archive_id, url_id, date, url, timeout_duration)
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
        return "Screenshot unsuccessful"


def cutycapt_screenshot(pics_out_path, archive_id, url_id, date, url, timeout_duration):
    command = "timeout {5}s xvfb-run --server-args=\"-screen 0, 1024x768x24\" " \
              "cutycapt --url='{0}' --out={1}{2}.{3}.{4}.png --delay=2000" \
        .format(url, pics_out_path, archive_id, url_id, date, timeout_duration)
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


async def remove_banner(page):
    """Execute js script on page to click button

        Parameters
        ----------
        page : pyppeteer.page.Page
            The page to go through

        References
        ----------
        .. [1] https://github.com/ukwa/webrender-puppeteer/blob/6fcc719d64dc19a4929c02d3a445a8283bee5195/renderer.js

        """
    await page.evaluate('''query => {
      const elements = [...document.querySelectorAll('wb_div')];
      const targetElement = elements.find(e => e.style.display.includes(query));
      targetElement.style.display = "none";
      }''', "block")


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
    lazy : int
        The max number of archive captures to take a screenshot of before moving on.
    be_lazy : bool
        Whether or not to take a maximum of screenshots per archive capture.

    """

    parser = argparse.ArgumentParser()

    parser.add_argument("--csv", type=str, help="Input CSV file with Archive urls")
    parser.add_argument("--db", type=str, help="Input DB file with urls")
    parser.add_argument("--picsout", type=str, help="Path of directory to output the screenshots")
    parser.add_argument("--indexcsv", type=str, help="The CSV file to write the index")
    parser.add_argument("--method", type=int, help="Which method to take the screenshots, "
                                                   "0 for chrome, 1 for puppeteer, 2 for cutycapt")
    parser.add_argument("--timeout", type=str, help="(optional) Specify duration before timeout, "
                                                    "in seconds, default 30 seconds")
    parser.add_argument("--lazy", type=int, help="(optional) Continues to the next archive after taking n pictures")
    parser.add_argument("--banner", action='store_true',
                        help="(optional) Include to keep banner, default removes banner")
    parser.add_argument("--async", type=int, help="(optional) Specify the number of coroutines, "
                                                  "default 1 coroutine, ")

    args = parser.parse_args()

    # some error checking
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
        print("Must specify output path for pictures")
        exit()
    if args.method is None:
        print("Must specify screenshot method\n")
        exit()

    pics_out_path = args.picsout + '/'
    screenshot_method = int(args.method)
    banner = args.banner

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

    if args.lazy is not None:
        be_lazy = True
        lazy = int(args.lazy)
    else:
        be_lazy = False
        lazy = None

    return csv_in_name, csv_out_name, pics_out_path, screenshot_method, use_csv, use_db, make_csv, \
        timeout_duration, lazy, be_lazy, banner, async_num


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
        datefmt:  format of the date in the message, date-month-year hour:minute:second AM/PM
        level:    minimum message level accepted

    """

    logging.basicConfig(filename=(pics_out_path + "archive_screenshot_log.txt"), filemode='a',
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        datefmt='%d-%b-%y %H:%M:%S %p', level=logging.INFO)


def main():
    csv_in_name, csv_out_name, pics_out_path, screenshot_method, use_csv, use_db, make_csv, timeout_duration, lazy, \
        be_lazy, banner, async_num = parse_args()
    set_up_logging(pics_out_path)
    print("Taking screenshots")
    if use_csv:
        screenshot_csv(csv_in_name, csv_out_name, pics_out_path, screenshot_method, timeout_duration, lazy, be_lazy,
                       banner, async_num)
    if use_db:
        screenshot_db(csv_out_name, pics_out_path, screenshot_method, make_csv, timeout_duration, lazy, be_lazy, banner)


main()
