It is common and useful to deploy your `SQLAdmin` or Litestar application
behind a reverse proxy like Nginx and enable `HTTPS` on the reverse proxy.

Running the app locally you would not face any issues but with HTTPS enabled
behind the reverse proxy you might see errors like this in your browser developer console:

```
Mixed Content: The page at '<URL>' was loaded over HTTPS, but requested an insecure script '<URL>'. This request has been blocked; the content must be served over HTTPS.
```

This means the CSS and Javascript files for the Admin were not loaded properly.
This is not exactly related to the `SQLAdmin` but more related to how
you are deploying your project.

For example if you are using `Uvicorn` as your ASGI server you can add the following options
to solve this issue:

- `--forwarded-allow-ips='*'`
- `--proxy-headers`

So it would be :

```shell
uvicorn <module>:<app> --forwarded-allow-ips='*' --proxy-headers
```

You can find more information and full docs for this at `Uvicorn` website
here at [ running behind nginx](https://www.uvicorn.org/deployment/#running-behind-nginx).
