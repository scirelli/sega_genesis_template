FROM scottyhardy/docker-wine:latest

RUN /usr/bin/entrypoint winetricks -q dotnet48

COPY ./Assembler/* /home/wineuser/app

WORKDIR /home/wineuser/app

ENTRYPOINT ["wine"]
CMD ["asm68k.exe"]
