ARG REPO
ARG VERSION
FROM $REPO/sliderule-ps-web:$VERSION AS web_img
FROM nginx:stable AS final
COPY --from=web_img /home/reg_user/ps/staticfiles /home/reg_user/ps/staticfiles/
RUN rm /etc/nginx/conf.d/default.conf
COPY ps-nginx.conf /etc/nginx/conf.d
EXPOSE 80